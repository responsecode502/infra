import structlog
from pathlib import Path
from dynaconf import Dynaconf
from invoke import task
from invoke.watchers import Responder

SCRIPT_DIR = Path(__file__).parent

log = structlog.get_logger()
cfg = Dynaconf(
    root_path=SCRIPT_DIR,
    load_dotenv=True,
    envvar_prefix=False,
    settings_files=["config.toml"],
)

@task
def set_root_password(ctx):
    ctx.config.update({"sudo" : {"password" : cfg.ROOT_PASSWORD}})
    log.info("[0] root password resolved")

@task(pre=[set_root_password])
def do_partitioning(ctx):
    log.info("[1] partitioning", step="start")
    ctx.sudo(f"mkfs.btrfs -f -L ROOT_PART {cfg.root_pt}", pty=True, hide=cfg.hide_output)
    ctx.sudo(f"fatlabel {cfg.efi_pt} EFI_PART", pty=True, hide=cfg.hide_output)
    ctx.sudo(f"mount {cfg.root_pt} {cfg.mnt}", pty=True, hide=cfg.hide_output)
    log.info("subvolumes are being created")
    for subvolume in ["@", "@home", "@snapshots"]:
        ctx.sudo(f"btrfs subvolume create {cfg.mnt}/{subvolume}", pty=True, hide=cfg.hide_output)
    ctx.sudo(f"umount {cfg.mnt}")
    log.info("[1] partitioning", step="finish")

@task(pre=[set_root_password])
def do_mounting_layout(ctx):
    log.info("[2] mounting layout", step="start")
    options = "noatime,compress=zstd,ssd,discard=async"
    for cmd in [
        f"mount -o {options},subvol=@ {cfg.root_pt} {cfg.mnt}",
        f"mkdir -p {cfg.mnt}/home {cfg.mnt}/.snapshots {cfg.mnt}/boot/efi {cfg.mnt}/mnt/btrfs-root",
        f"mount -o {options},subvol=@home {cfg.root_pt} {cfg.mnt}/home",
        f"mount -o {options},subvol=@snapshots {cfg.root_pt} {cfg.mnt}/.snapshots",
        f"mount {cfg.efi_pt} {cfg.mnt}/boot/efi"
    ]:
        ctx.sudo(cmd, pty=True, hide=cfg.hide_output)
    log.info("[2] mounting layout", step="finish") 

@task(pre=[set_root_password])
def install_base(ctx):
    log.info("[3] installing base", step="start")
    BOOTSTRAP_PACKAGES = [
        "base-system",
        "btrfs-progs",
        "grub-x86_64-efi",
        "os-prober",
        "grub-btrfs"
    ]
    for cmd in [
        f"mkdir -p {cfg.mnt}/var/db/xbps/keys",
        f"cp -R /var/db/xbps/keys/* {cfg.mnt}/var/db/xbps/keys/",
        f"xbps-install -S -y -R {cfg.xbps_repo} -r {cfg.mnt} {' '.join(BOOTSTRAP_PACKAGES)}"
    ]:
        ctx.sudo(cmd, pty=True, hide=cfg.hide_output)
    log.info("[3] installing base", step="finish")

@task(pre=[set_root_password])
def do_chroot(ctx):
    log.info("[4] chroot", step="start")
    ctx.sudo(f"mount --make-rslave {cfg.mnt}")
    for fs in ["dev", "proc", "sys", "run"]:
        ctx.sudo(f"mount --rbind /{fs} {cfg.mnt}/{fs}")
    ctx.sudo(f"mount --rbind /sys/firmware/efi/efivars {cfg.mnt}/sys/firmware/efi/efivars")
    ctx.sudo(f"cp /etc/resolv.conf {cfg.mnt}/etc/")

    for cmd in [ 
        f"bash -c 'echo {cfg.system.hostname} > /etc/hostname'",
        f"bash -c 'echo \"LANG=en_US.UTF-8\" > /etc/locale.conf'",
        f"bash -c 'echo \"en_US.UTF-8 UTF-8\" >> /etc/default/libc-locales'",
        f"xbps-reconfigure -f glibc-locales",
        f"ln -sf /usr/share/zoneinfo/{cfg.system.timezone} /etc/localtime"
    ]:
        ctx.sudo(f"chroot {cfg.mnt} {cmd}", pty=True, hide=cfg.hide_output)

    log.info("setting root password")
    pass_responder = Responder(pattern=r"New password:", response=f"{cfg.ROOT_PASSWORD}\n")
    retry_responder = Responder(pattern=r"Retype new password:", response=f"{cfg.ROOT_PASSWORD}\n")

    ctx.sudo(
        f"chroot {cfg.mnt} passwd root", 
        watchers=[pass_responder, retry_responder], 
        pty=True,
        hide=cfg.hide_output
    )

    log.info("deploying rollback script")
    ctx.sudo(f"mkdir -p {cfg.mnt}/usr/bin")
    rollback_script_src = SCRIPT_DIR.resolve() / "system/usr/bin/rollback"
    ctx.sudo(f"cp -a {rollback_script_src} {cfg.mnt}/usr/bin/rollback")
    ctx.sudo(f"chmod +x {cfg.mnt}/usr/bin/rollback")

    log.info("deploying fstab")
    fstab_src = SCRIPT_DIR.resolve() / "system/etc/fstab"
    ctx.sudo(f"cp {fstab_src} {cfg.mnt}/etc/fstab")

    log.info("configuring grub and btrbk")
    for cmd in [ 
        f"bash -c 'echo \"GRUB_DISABLE_OS_PROBER=false\" >> /etc/default/grub'",
        f"grub-install --target=x86_64-efi --efi-directory=/boot/efi --bootloader-id=void --recheck",
        f"xbps-reconfigure -fa",

        "xbps-install -S --yes",
        "xbps-install -u xbps --yes",
        "xbps-install btrbk --yes"
    ]:
        ctx.sudo(f"chroot {cfg.mnt} {cmd}", pty=True, hide=cfg.hide_output)
    ctx.sudo(f"mkdir -p {cfg.mnt}/etc/btrbk", pty=True, hide=cfg.hide_output)
    
    log.info("deploying btrbk")
    btrbk_src = SCRIPT_DIR.resolve() / "system/etc/btrbk/btrbk.conf"
    ctx.sudo(f"mkdir -p {cfg.mnt}/etc/btrbk")
    ctx.sudo(f"cp {btrbk_src} {cfg.mnt}/etc/btrbk/btrbk.conf")

    btrfs_root_path = f"{cfg.mnt}/mnt/btrfs-root"

    log.info("creating pure_system snapshot")
    for cmd in [
        f"mkdir -p {btrfs_root_path}",
        f"mount -o subvolid=5 {cfg.root_pt} {btrfs_root_path}",
        f"btrfs subvolume snapshot -r {btrfs_root_path}/@ {btrfs_root_path}/@snapshots/@.pure_system",
        f"btrfs subvolume snapshot -r {btrfs_root_path}/@home {btrfs_root_path}/@snapshots/@home.pure_system",
        f"umount {btrfs_root_path}",
        f"umount -R {cfg.mnt}"
    ]:
        ctx.sudo(cmd, pty=True, hide=cfg.hide_output)
        
    log.info("[4] chroot", step="finish")

@task
def do_poweroff(ctx):
    ctx.sudo("poweroff")

@task(
    pre = [
        set_root_password,
        do_partitioning,
        do_mounting_layout,
        install_base,
        do_chroot
    ],
    post = [
        do_poweroff
    ]
)
def setup_system(c):
    pass

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
    log.info("[0] root password updated")

@task(pre=[set_root_password])
def do_partitioning(ctx):
    log.info("[1] partitioning", step="start")
    ctx.sudo(f"mkfs.btrfs -f -L ROOT_PART {cfg.root_pt}", pty=True, hide=True)
    ctx.sudo(f"fatlabel {cfg.efi_pt} EFI_PART", pty=True, hide=True)
    ctx.sudo(f"mount {cfg.root_pt} {cfg.mnt}")
    log.info("subvolumes are being created")
    for subvolume in ["@", "@home", "@snapshots"]:
        ctx.sudo(f"btrfs subvolume create {cfg.mnt}/{subvolume}", pty=True, hide=True)
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
        ctx.sudo(cmd, pty=True, hide=True)
    log.info("[2] mounting layout", step="finish") 

@task(pre=[set_root_password])
def install_base(ctx):
    log.info("[3] installing base", step="start")
    BOOTSTRAP_PACKAGES = ["base-system", "btrfs-progs", "grub-x86_64-efi", "os-prober"]
    bootstrap_commands = [
        f"mkdir -p {cfg.mnt}/var/db/xbps/keys",
        f"cp -R /var/db/xbps/keys/* {cfg.mnt}/var/db/xbps/keys/",
        f"xbps-install -S -y -R {cfg.xbps_repo} -r {cfg.mnt} {' '.join(BOOTSTRAP_PACKAGES)}"
    ]
    for cmd in bootstrap_commands:
        ctx.sudo(cmd, pty=True, hide=True)
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
        ctx.sudo(f"chroot {cfg.mnt} {cmd}", pty=True, hide=True)
    
    pass_responder = Responder(pattern=r"New password:", response=f"{cfg.ROOT_PASSWORD}\n")
    retry_responder = Responder(pattern=r"Retype new password:", response=f"{cfg.ROOT_PASSWORD}\n")

    ctx.sudo(
        f"chroot {cfg.mnt} passwd root", 
        watchers=[pass_responder, retry_responder], 
        pty=True,
        hide=True
    )
    
    root_uuid = c.sudo(f"blkid -o value -s UUID {PART_ROOT}", hide=True).stdout.strip()
    efi_uuid = c.sudo(f"blkid -o value -s UUID {PART_EFI}", hide=True).stdout.strip()
    
    fstab_text = FSTAB.format(root_uuid=root_uuid, efi_uuid=efi_uuid)
    c.sudo(f"bash -c \"cat << 'EOF' > {MNT}/etc/fstab\n{fstab_text}\nEOF\"")

    c.sudo(f"{in_chroot} bash -c 'echo \"GRUB_DISABLE_OS_PROBER=false\" >> /etc/default/grub'")
    c.sudo(f"{in_chroot} grub-install --target=x86_64-efi --efi-directory=/boot/efi --bootloader-id=void --recheck", pty=True)
    c.sudo(f"{in_chroot} xbps-reconfigure -fa", pty=True)
    #c.sudo(f"umount -R {MNT}")
    
    logger.info("phase 4: chroot", step = "finish")




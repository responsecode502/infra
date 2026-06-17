import os
import tomllib
import structlog
from pathlib import Path
from dotenv import load_dotenv
from invoke import task
from invoke.watchers import Responder
from invoke.exceptions import Exit

logger = structlog.get_logger()

BASE_DIR = Path(__file__).parent

config_path = BASE_DIR / "config.toml"
if not config_path.exists():
    raise Exit(f"Config {config_path} not found", code = 1)
with open(config_path, "rb") as f:
    config = tomllib.load(f)

HARDWARE = config["hardware"]
REPOS = config["repos"]
SYSTEM = config["system"]
TEMPLATES = config["templates"]

PART_EFI = HARDWARE["part_efi"]
PART_ROOT = HARDWARE["part_root"]
MNT = HARDWARE["mnt"]

XBPS_REPO = REPOS["xbps"]

HOSTNAME = SYSTEM["hostname"]
TIMEZONE = SYSTEM["timezone"]

FSTAB = TEMPLATES["fstab"]
BTRBK = TEMPLATES["btrbk"]

load_dotenv(dotenv_path = BASE_DIR / ".env")

BOOTSTRAP_PACKAGES = ["base-system", "btrfs-progs", "grub-x86_64-efi", "os-prober"]

@task
def set_root_password(c):
    if not (password := os.getenv("ROOT_PASSWORD")):
        raise Exit("ROOT_PASSWORD missing", code = 1)
    logger.info("root password updated")
    c.config.update({"sudo" : {"password" : password}})

@task(pre=[set_root_password])
def do_partitioning(c):
    logger.info("phase 1: partitioning", step = "start")
    c.sudo(f"mkfs.btrfs -f {PART_ROOT}", pty=True)
    c.sudo(f"mount {PART_ROOT} {MNT}")
    for sv in ["@", "@home", "@snapshots"]:
        c.sudo(f"btrfs subvolume create {MNT}/{sv}", pty=True)
    c.sudo(f"umount {MNT}")
    logger.info("phase 1: partitioning", step = "finish")

@task(pre=[set_root_password])
def do_mounting_layout(c):
    logger.info("phase 2: mounting layout", step = "start")
    options = "noatime,compress=zstd,ssd,discard=async"
    mount_commands = [
        f"mount -o {options},subvol=@ {PART_ROOT} {MNT}",
        f"mkdir -p {MNT}/home {MNT}/.snapshots {MNT}/boot/efi {MNT}/mnt/btrfs-root",
        f"mount -o {options},subvol=@home {PART_ROOT} {MNT}/home",
        f"mount -o {options},subvol=@snapshots {PART_ROOT} {MNT}/.snapshots",
        f"mount {PART_EFI} {MNT}/boot/efi"
    ]
    for cmd in mount_commands:
        c.sudo(cmd, pty=True)
    logger.info("phase 2: mounting layout", step = "finish") 

@task(pre=[set_root_password])
def do_bootstrap(c):
    logger.info("phase 3: bootstrap OS core", step = "start")    
    bootstrap_commands = [
        f"mkdir -p {MNT}/var/db/xbps/keys",
        f"cp -R /var/db/xbps/keys/* {MNT}/var/db/xbps/keys/",
        f"xbps-install -S -y -R {XBPS_REPO} -r {MNT} {' '.join(BOOTSTRAP_PACKAGES)}"
    ]
    for cmd in bootstrap_commands:
        c.sudo(cmd, pty=True)
    logger.info("phase 3: bootstrap OS core", step = "finish")

@task(pre=[set_root_password])
def do_chroot(c):
    logger.info("phase 4: chroot", step = "start")
    c.sudo(f"mount --make-rslave {MNT}")
    for fs in ["dev", "proc", "sys", "run"]:
        c.sudo(f"mount --rbind /{fs} {MNT}/{fs}")
    c.sudo(f"mount --rbind /sys/firmware/efi/efivars {MNT}/sys/firmware/efi/efivars")
    c.sudo(f"cp /etc/resolv.conf {MNT}/etc/")

    in_chroot = f"chroot {MNT}"

    c.sudo(f"{in_chroot} bash -c 'echo {HOSTNAME} > /etc/hostname'")
    c.sudo(f"{in_chroot} bash -c 'echo \"LANG=en_US.UTF-8\" > /etc/locale.conf'")
    c.sudo(f"{in_chroot} bash -c 'echo \"en_US.UTF-8 UTF-8\" >> /etc/default/libc-locales'")
    c.sudo(f"{in_chroot} xbps-reconfigure -f glibc-locales", pty=True)
    c.sudo(f"{in_chroot} ln -sf /usr/share/zoneinfo/{TIMEZONE} /etc/localtime")

    _response = f"{os.getenv('ROOT_PASSWORD')}\n"
    pass_responder = Responder(pattern=r"New password:", response=_response)
    retry_responder = Responder(pattern=r"Retype new password:", response=_response)

    c.sudo(
        f"chroot {MNT} passwd root", 
        watchers=[pass_responder, retry_responder], 
        pty=True
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

@task(pre=[set_root_password])
def setup_btrbk(c):
    logger.info("phase 5: setup btrbk", step = "start")
    xbps_init_script = f"""
SSL_NO_VERIFY=1 xbps-install -S --yes

xbps-install -u xbps --yes

xbps-install btrbk --yes

mkdir -p /etc/btrbk
cat << 'EOF' > /etc/btrbk/btrbk.conf
{BTRBK}
EOF

mkdir -p /mnt/btrfs-root
mount -o subvolid=5 {PART_ROOT} /mnt/btrfs-root
btrfs subvolume snapshot /mnt/btrfs-root/@ /mnt/btrfs-root/@snapshots/@.pure_system
btrfs subvolume snapshot /mnt/btrfs-root/@home /mnt/btrfs-root/@snapshots/@home.pure_system
umount /mnt/btrfs-root
"""

    c.sudo(f"chroot {MNT} bash", input=xbps_init_script, pty=True)
    c.sudo(f"umount -R {MNT}")
    
    logger.info("phase 5: setup btrbk", step = "finish")

    

@task
def finalize(c):
    logger.info("Process finished! Rebooting in 10 seconds...")

    import time
    for _ in range(20):
        time.sleep(0.5)
    c.sudo("reboot")

@task(
    pre = [
        set_root_password,
        do_partitioning,
        do_mounting_layout,
        do_bootstrap,
        do_chroot,
        setup_btrbk
    ],
    post = [
        finalize
    ]
)
def setup_system(c):
    pass

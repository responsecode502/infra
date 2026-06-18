# Encryption & Deployment Guide

## Encrypt `.env`

1. Run `set-envkey.sh` and enter the passphrase — it will create `.envkey` inside the chosen profile  
   (Check `.profile` and use `select.sh` to change it)
2. `cd` into the current profile folder and run:  
   `uv run python crypt.py --encrypt`
3. Your `.env` is now encrypted to `.env.enc`

---

## Decrypt `.env`

1. Run `set-envkey.sh` to create `.envkey`
2. `cd` into the current profile directory and run:  
   `uv run python crypt.py --decrypt`
3. You now have `.env` decrypted from `.env.enc`

---

## Deploy on a Live System

1. Run `select.sh` if needed
2. Run `set-envkey.sh`
3. Run `run.sh` with `sudo`

From the root repo directory, this can be done with:

```bash
./select.sh your_profile_here && ./set-envkey.sh your_envkey_here && sudo ./run.sh

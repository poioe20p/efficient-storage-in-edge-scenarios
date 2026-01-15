# Run the lab setup and validate connectivity

This repo is designed to run **inside the Ubuntu VM** (Docker, networking, iptables, OS-Ken controller).

## 1) SSH into the Ubuntu VM from Windows

From **Windows PowerShell** (host), connect via the VirtualBox port-forward rule (host `localhost:2222` → guest `:22`).

- Username comes from `{user_env_variable}`

This workflow assumes you have **key-based SSH** configured, so you can connect without interactive prompts.

Run:

```powershell
ssh -v -p 2222 ${env:{user_env_variable}}@localhost
```

If your SSH session prompts for credentials, set up key-based access in step 1.1 first.

### 1.1) Set up key-based SSH (recommended)

Configure **key-based SSH** so you can connect and run commands non-interactively.

From **Windows PowerShell**:

1) Generate a key (if you do not already have one):

```powershell
ssh-keygen -t ed25519
```

2) Copy the public key into the VM user’s `authorized_keys` (requires one successful authenticated SSH connection if not already configured):

```powershell
Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub | ssh -p 2222 ${env:{user_env_variable}}@localhost "mkdir -p ~/.ssh; chmod 700 ~/.ssh; cat >> ~/.ssh/authorized_keys; chmod 600 ~/.ssh/authorized_keys"
```

3) Verify key-based auth works:

```powershell
ssh -p 2222 -o BatchMode=yes ${env:{user_env_variable}}@localhost "echo SSH_KEY_OK"
```

If this prints `SSH_KEY_OK` without interactive prompts, you are set.

Notes:
- `-v` prints verbose diagnostics; it is helpful if the connection fails.
- If `localhost` works but `10.0.2.15` does not, that’s expected when the VM uses NAT networking.

## 2) Go to the repo inside the VM

If you are using a VirtualBox Shared Folder, the repo is typically available under:

```bash
cd /media/sf_efficient-storage-in-edge-scenarios
```

Then go to scripts:

```bash
cd scripts
```

(If access is denied, ensure your user is in the `vboxsf` group: `sudo usermod -aG vboxsf <your-user>` and log out/in.)

## 3) Run the setup

From the `scripts/` directory:

```bash
./build_setup.sh
```

This should complete with a success message similar to:

- `Build and setup of networks completed successfully.`

## 3.1) Verify containers are running

`build_setup.sh` (including `build_network_1.sh` and `build_network_2.sh`) should leave a set of containers running.

From anywhere in the VM, run:

```bash
docker ps --format '{{.Names}}' | sort
```

Minimum expected container names:

- `ovs`
- `nat-router`
- `mongodb-config-server`
- `mongodb-router`
- `mongodb-n1`
- `mongodb-n2`
- `container1`
- `container2`
- `container3`
- `container4`
- `container5`

Optional (only if your `build_setup.sh` starts the controller container(s) successfully):

- `osken`
- `osken_2`

Quick automated check (exits non-zero if any required container is missing):

```bash
required=(
	ovs nat-router mongodb-config-server mongodb-router mongodb-n1 mongodb-n2
	container1 container2 container3 container4 container5
)

missing=0
for name in "${required[@]}"; do
	if ! docker ps --format '{{.Names}}' | grep -Fxq "$name"; then
		echo "Missing container: $name" >&2
		missing=1
	fi
done

if [[ $missing -ne 0 ]]; then
	echo "One or more required containers are not running." >&2
	exit 1
fi

echo "All required containers are running."
```

## 4) Validate connectivity

From the `scripts/` directory:

```bash
cd ..
./tests/run_tests.sh all
```

Alternative (after step 1.1): run the tests from Windows without an interactive login:

```powershell
ssh -p 2222 ${env:{user_env_variable}}@localhost "cd /media/sf_efficient-storage-in-edge-scenarios && bash source/tests/run_tests.sh all"
```

Expected outcome:
- You should see multiple ping checks reported as reachable.
- If this script completes without failing critical pings, it means your changes **still allow connectivity across LAN1, LAN2, cross-LAN, and Internet targets**, and the lab is behaving as expected.

If something fails:
- Re-run with the same command and capture the failing source/target pair.
- Check container status: `docker ps`
- Check router/NAT container logs if Internet pings fail.
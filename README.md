# PAW Proxy Pilot

**PAW Proxy Pilot** is a secure, web-based GUI for managing Squid Proxy domain allow/block lists, designed specifically for Privileged Access Workstations (PAWs). This tool gives organizations a simple, powerful interface to tightly control internet access for privileged endpoints.

## Features

- **Web-Based GUI:** Manage Squid allow/block lists from your browser.
- **PAW Focus:** Purpose-built for Privileged Access Workstations and secure environments.
- **Full Allow/Block Management:** Add, remove, sort, and bulk-manage allowed, blocked, or unsorted domains.
- **Automated Setup:** Installs and configures all required dependencies, Squid, and system services.
- **Easy Updates:** Update script checks for and applies updates, restarting services if needed.
- **Client Visibility:** View a summary of recent client IPs using the proxy.
- **Real-Time Application:** Changes are validated and applied immediately to the Squid proxy.
- **Integrated Restart:** Restart Squid directly from the web UI when changes are pending.
- **Secure by Design:** PAM authentication (Linux user/password) for admin access.

## Table of Contents

- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Usage](#usage)
- [Updating](#updating)
- [How it Works](#how-it-works)
- [Security](#security)
- [Contributing](#contributing)
- [License](#license)

## Requirements

- Linux server (tested on Ubuntu/Debian; may work on others)
- Python 3.x
- Bash shell
- sudo privileges for installation and updating

**No pre-existing Squid install is necessary** — the setup script will install and configure everything you need!

## Installation

Clone the repository and run the install script:

```bash
git clone https://github.com/andrew-kemp/squid_allow_app.git /opt/paw_proxy_pilot
cd /opt/paw_proxy_pilot
sudo bash install.sh
```

The installer will:

- Install all required packages (including Squid, nginx, Python, PAM)
- Set up the PAW Proxy Pilot web interface
- Generate SSL certs and configure nginx as a reverse proxy
- Configure Squid for PAW domain management
- Enable and start system services

## Usage

After installation, access the web GUI at:

```
https://<server-ip>/
```

- Log in with your Linux administrator credentials (PAM authentication)
- Add, remove, allow, or block domains directly from the interface
- Restart Squid from the UI when prompted after changes

## Updating

To update the application, simply run:

```bash
sudo bash update.sh
```

This will fetch the latest version, update all files, and restart services as needed.

## How it Works

- The web GUI manages domain lists for Squid (allowed, blocked, unsorted)
- Python/Flask powers the backend; shell scripts manage OS and Squid integration
- All changes are validated and applied instantly; restart Squid via the UI to take effect
- Systemd and nginx are configured for security and performance

## Security

- Web interface requires Linux (PAM) authentication
- Restrict access to trusted administrators only
- Run behind a firewall or limit access via network controls
- Change all default credentials immediately after installation
- SSL (self-signed by default) is enabled for the web interface

## Contributing

Feedback, bug reports, and PRs are welcome! Please open an issue or submit a pull request.

## License

[MIT License](LICENSE)

---

*For questions or support, please open an issue on GitHub.*

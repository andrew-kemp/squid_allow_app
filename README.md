# Squid PAW Manager

A web-based GUI for Squid Proxy, designed specifically for controlling and managing access for Privileged Access Workstations (PAWs). This tool provides an intuitive interface for managing allow-lists, enabling organizations to tightly control internet access for privileged endpoints.

## Features

- **Web-Based GUI:** Manage Squid allow-lists from a browser.
- **Purpose-Built for PAWs:** Tailored for controlling web access from Privileged Access Workstations.
- **Automated Setup:** Installs all required dependencies and also sets up and configures Squid.
- **Easy Updates:** Update script seamlessly checks for and applies updates, restarting the service as needed.
- **Cross-Platform:** Built with Python and Shell scripts for maximum compatibility.

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

**No pre-existing Squid installation necessary** — the setup script will install and configure Squid for you.

## Installation

Download and run the installation script as root:

```bash
curl -O https://raw.githubusercontent.com/andrew-kemp/squid_allow_app/main/install.sh
sudo bash install.sh
```

The installer will:

- Install all required services and dependencies (including Squid)
- Set up the Squid PAW Manager web interface
- Configure Squid for PAW access management
- Create and enable the necessary system services

## Usage

After installation, access the web GUI by navigating to:

```
http://<server-ip>:<configured-port>/
```

- Log in with your administrator credentials (default or as configured during installation)
- Add, remove, or manage PAW allow-lists directly from the interface
- All changes apply in real-time to the Squid proxy

## Updating

To check for updates and update the application, run:

```bash
sudo bash update.sh
```

This will:

- Fetch the latest version of Squid PAW Manager and its components
- Update files as needed
- Restart the service so changes take effect

## How it Works

- The web GUI manages Squid allow-lists and configuration files specific to PAW access
- All changes made via the GUI are validated and applied immediately
- Python handles the backend logic; shell scripts manage system and Squid-level integration

## Security

- Restrict web interface access to trusted administrators only
- Run behind a firewall or use network-level access controls
- Change all default passwords immediately after installation

## Contributing

Feedback, bug reports, and pull requests are welcome! Please open an issue or submit a PR through this repository.

## License

[MIT License](LICENSE)

---

*For questions or support, please open an issue on GitHub.*

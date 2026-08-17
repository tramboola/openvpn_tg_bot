# Button-driven OpenVPN bot design

## Goal

Make the existing bot quick to install on a single Ubuntu VPS and usable from Telegram without memorizing commands.

## Installation

The repository provides `install.sh`. It installs Docker Engine and Docker Compose on Ubuntu when they are absent, asks only for the BotFather token and the administrator's numeric Telegram user ID, writes a protected `.env`, creates persistent application data, builds the bot, and starts it.

The user is not asked for an IP address or port. The bot discovers the VPS public IPv4 address when OpenVPN is initialized. UDP always uses `1194/udp`; TCP always uses `443/tcp`. Failure to discover a public address or an occupied/reserved Docker port is reported without silently choosing a different endpoint.

## Telegram flow

`/start` displays a persistent keyboard:

- `➕ Создать конфиг`
- `📋 Конфиги`
- `📊 Статус`
- `⚙️ Настройки`

On a new installation the bot instead shows `UDP` and `TCP` buttons. The administrator chooses one protocol, reviews the detected endpoint, and confirms initialization. Only the selected OpenVPN container is created. The selected server protocol applies to every client profile.

Creating a profile asks for a short device name, validates it, creates the certificate, and sends an `.ovpn` document. Commands remain as compatibility entry points, but buttons are the primary interface.

The profile list shows active certificates. Each row offers download and revoke actions. Revocation always has a separate confirmation step and is described as revoking access because the bot cannot delete a file already stored on a client device.

## Profile names and suffix

Certificate common names remain independent from the display suffix and end with the server protocol. A profile named `iphone` on UDP therefore has a certificate common name such as `iphone_udp`.

The configurable suffix affects only the Telegram document filename. With suffix `prague`, the file is `iphone-prague-udp.ovpn`. Changing the suffix does not rename or invalidate existing certificates. The suffix is optional and accepts a bounded portable subset of letters, digits, `_`, and `-`.

## Persistent state

The bot stores the selected protocol, public host, fixed port, and filename suffix in an atomically replaced JSON file under `/app/data`. Docker Compose bind-mounts the host `data` directory there. Secrets remain in `.env`, not in the state file.

## Safety and recovery

Every callback repeats the administrator check. Mutating OpenVPN operations are serialized to prevent simultaneous initialization, creation, or revocation races. Full shutdown and PKI deletion require explicit confirmation. Partial Docker failures produce an error instead of an unconditional success message.

The bot image retains Docker socket access for compatibility with the current architecture. This is an accepted MVP trade-off for a private administrator-only VPS; the risk is documented. The OpenVPN image is configurable and defaults to the existing compatible image pinned to tag `2.4`.

## Testing

Unit tests cover filename construction, name and suffix validation, JSON state persistence, public IPv4 parsing and fallback, single-protocol Docker command construction, active-certificate parsing, and Telegram keyboard/callback registration. Existing protocol adaptation and address parsing tests remain green. Deployment configuration is validated without launching or deleting real Docker resources.


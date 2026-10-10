# Security policy

## Reporting a vulnerability

Use GitHub's private vulnerability reporting feature for this repository. Do not
open a public issue for suspected authentication bypass, cross-researcher data
exposure, command execution, credential disclosure, or access to private worker
or dataset information.

Include the affected component and version, reproduction steps using synthetic
or non-sensitive data, impact, and any temporary mitigation. Do not test against
another researcher's identity or dataset.

## Data handling

Never commit or attach source neuroimages, participant identifiers, protected
health information, OAuth tokens, passwords, client secrets, worker tokens,
private keys, private host addresses, or local path inventories. See
`docs/security-and-data-boundaries.md` for the intended boundaries.

Only the latest beta release is currently supported for security fixes.

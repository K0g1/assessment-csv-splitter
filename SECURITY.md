# Security

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub's security advisory feature. Do not include real patient data, identifiers, source exports, or audit manifests in a public issue.

## Data handling

The tool runs locally. It does not make network requests, upload files, send telemetry, or depend on a remote service. Real datasets must never be committed to this repository.

The destination is staged and audited before publication. Existing destinations are never overwritten. Local audit manifests contain routing identifiers and should be protected with the same controls as the source dataset.

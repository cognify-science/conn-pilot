# Connection verification checklist

Run these checks after configuring any AI client.

1. The client lists a server named `conn-pilot` and reports an authenticated
   connection.
2. Ask the server for identity-scoped capabilities and confirm that the returned
   identity belongs to the expected researcher.
3. List supported experiment families and confirm that seed-to-voxel and
   ROI-to-ROI discovery works.
4. List visible datasets. Confirm that no dataset outside the researcher's
   authorization boundary appears.
5. Read worker health. Treat this as operational status, not permission to run.
6. Ask for parameter evidence for one supported method. Confirm that evidence
   identifiers and corpus/version information are returned.
7. Do not submit a project during verification.

Failure categories should remain distinct:

- authentication failure: login, allowlist, scope, or client registration;
- authorization failure: identity lacks access to an object or operation;
- validation failure: the scientific request is outside the executable contract;
- worker failure: an accepted job cannot currently execute;
- scientific uncertainty: the system cannot justify a methodological or
  inferential conclusion from available evidence.

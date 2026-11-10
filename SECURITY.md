
# Runtime verification and remaining limitations

The application uses Chroma `PersistentClient` inside the Python process. It does not start or expose a Chroma HTTP server and it never accepts collection configuration, embedding-function code, model repositories, or `trust_remote_code` options through its API.

The dependency audit on 10 November 2026 still reports Chroma 1.5.9 advisories PYSEC-2026-311, PYSEC-2026-3813, PYSEC-2026-3814 and PYSEC-2026-3815 (one finding is duplicated by the advisory feed). No fixed version is listed by that feed. These concern Chroma server collection/authorization endpoints. They remain dependency findings: do not expose a Chroma server or enable user-selected embedding functions. Reassess and update when upstream publishes fixes; embedded use is not a claim that the dependency is vulnerability-free.

Other reported backend findings were addressed by updating the affected runtime and development packages, then rerunning checks. Frontend `npm audit` reports zero known vulnerabilities after dependency updates. Audit results are time-sensitive.

Use HTTPS and `COOKIE_SECURE=true` in production. For separate frontend/backend sites use `COOKIE_SAMESITE=none` with secure cookies and exact `CORS_ORIGINS`; same-site deployment is simpler. All cookie-authenticated mutations require `X-Prism-Client: web`. Passwords use salted PBKDF2-SHA256, sessions use random tokens stored hashed in SQLite, and public signup cannot create administrators.

Candidate discovery is private by default. Applying deliberately shares the profile with the job's recruiter workspace. Internal notes are not returned to candidates. Workspace invitations are bound to the named email, expire in seven days, and can only be redeemed once. Removing a member revokes their sessions. Invitation codes are displayed for manual sharing; Prism does not send email.

Back up the SQLite database before deployment and validate migrations on a copy. Existing unowned profiles/runs remain inaccessible to ordinary users until explicitly assigned with `migrate_legacy.py`; they are never automatically assigned to a new signup. Index recovery reads source profiles without replacing them with demo data.

This is a tested local MVP, not an enterprise security certification. Live NVIDIA calls, external account integrations, email verification/recovery, independent ranking evaluation, production capacity, backups/restores and operational monitoring still need validation in the deployment environment.

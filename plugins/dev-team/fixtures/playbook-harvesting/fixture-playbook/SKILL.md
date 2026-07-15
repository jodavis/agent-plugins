# stand-up-fixture-service

Stand up a new service from the shared scaffold template, following the same construction
order used for `orders-service` and `billing-service`.

## Steps

1. **Stamp from the template.** Copy the `stand-up-fixture-service` template output into the
   new service's directory unmodified. Commit this pristine output before making any other
   change, so a later diff against the template shows exactly what was customized.

   *Validation gate:* `git status` reports a clean working tree immediately after this commit;
   `diff -r <new-service-dir> <template-output-dir>` reports no differences.

2. **Strip and replace.** Replace the `{{SERVICE_NAME}}` and `{{LOG_FORMAT}}` placeholder
   tokens in `service.yaml`, `README.md`, and `src/main.py` with the new service's real name
   and a `json` logging format (the team's structured-logging standard; use `text` only as a
   documented, one-off exception).

   *Validation gate:* `grep -r "{{" .` reports no remaining placeholder tokens.

3. **Validate configuration.** Confirm `service.yaml` matches the schema in
   `service-yaml-schema.md`: `name`, `port`, and `logging.format` are all present and
   correctly typed. Manual fallback until a standalone validator script exists: review the
   file by hand against the schema. (TODO: extract a `validate-service-yaml` script so this
   step can run unattended.)

   *Validation gate:* every field in `service-yaml-schema.md` is present in `service.yaml`
   with the correct type, confirmed by the extracted validator once it exists, or by manual
   review until then.

## Notes

- Services built from this playbook so far: `orders-service`, `billing-service`.

# Publishing the integration

The authorized community repository is expected at
`https://github.com/amithalp/pima-force-ha-integration`. Retain the original Git
history and the attribution in `AUTHORS.md`.

## First publication

1. Retain the MIT `LICENSE` file and attribution history.
2. Create the GitHub repository with Issues enabled and a useful description.
3. Push the full repository and confirm all jobs in `validate.yaml` pass.
4. Add the repository to HACS as a custom integration and test a clean install.
5. Tag the same version declared in `custom_components/pima/manifest.json`:
   `v1.20.0`.
6. Create a full GitHub release from that tag using `RELEASE_NOTES.md`.

Do not publish a release asset containing development ZIP archives, panel
documentation supplied under separate terms, real logs, credentials, private
addresses, personal names or unrelated automation files.

## Later releases

1. Update `CHANGELOG.md` and `RELEASE_NOTES.md`.
2. Increase the manifest version using semantic versioning.
3. Run the complete local test suite and review `git diff --check`.
4. Open a pull request and require unit-test, HACS and hassfest checks.
5. Test installation or upgrade through HACS.
6. Create a matching tag and full GitHub release.

Home Assistant Brands and HACS default-list submission are optional later
distribution steps; neither is required for users to install a public
repository as a HACS custom repository.

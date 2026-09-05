import json
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
INTEGRATION = ROOT / "custom_components" / "pima"


class IntegrationMetadataTests(unittest.TestCase):
    def test_manifest_enables_single_config_entry(self):
        manifest = json.loads((INTEGRATION / "manifest.json").read_text(encoding="utf-8"))
        self.assertTrue(manifest["config_flow"])
        self.assertTrue(manifest["single_config_entry"])
        self.assertEqual(manifest["integration_type"], "hub")
        self.assertIn("@amithalp", manifest["codeowners"])
        self.assertEqual(manifest["version"], "1.21.0")
        self.assertEqual(manifest["codeowners"], ["@amithalp"])
        self.assertEqual(
            manifest["documentation"],
            "https://github.com/amithalp/pima-force-ha-integration",
        )

    def test_config_flow_and_translations_are_packaged(self):
        self.assertTrue((INTEGRATION / "config_flow.py").is_file())
        strings = json.loads((INTEGRATION / "strings.json").read_text(encoding="utf-8"))
        english = json.loads(
            (INTEGRATION / "translations" / "en.json").read_text(encoding="utf-8")
        )
        hebrew = json.loads(
            (INTEGRATION / "translations" / "he.json").read_text(encoding="utf-8")
        )
        for content in (strings, english, hebrew):
            self.assertIn("user", content["config"]["step"])
            self.assertIn("reconfigure", content["config"]["step"])

    def test_every_platform_supports_config_entry_setup(self):
        for filename in (
            "alarm_control_panel.py",
            "binary_sensor.py",
            "button.py",
            "sensor.py",
            "switch.py",
            "siren.py",
        ):
            source = (INTEGRATION / filename).read_text(encoding="utf-8")
            self.assertIn("async def async_setup_entry(", source, filename)

    def test_release_documentation_is_packaged(self):
        for filename in (
            "AUTHORS.md",
            "CHANGELOG.md",
            "CONTRIBUTING.md",
            "LICENSE",
            "README.md",
            "RELEASE_CHECKLIST.md",
            "RELEASE_NOTES.md",
            "SECURITY.md",
            "docs/PUBLISHING.md",
        ):
            self.assertTrue((ROOT / filename).is_file(), filename)

        license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("MIT License", license_text)
        self.assertIn("@aarbelle", license_text)
        self.assertIn("amithalp", license_text)

    def test_public_documentation_is_home_assistant_only(self):
        for filename in (
            "README.md",
            "RELEASE_CHECKLIST.md",
            "RELEASE_NOTES.md",
            "CONTRIBUTING.md",
        ):
            content = (ROOT / filename).read_text(encoding="utf-8").lower()
            self.assertNotIn("hadb", content, filename)
            self.assertNotIn("hubitat", content, filename)


if __name__ == "__main__":
    unittest.main()

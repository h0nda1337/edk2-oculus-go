"""Check how the UFS-only sysfs reader distinguishes an absent group from failure."""
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from collect_ufs_binding import DEVICE, query_links


def fixture(targets, denied=None):
    def shell(command, option, path):
        if command == "ls":
            assert option == "-1a" and path == DEVICE
            return subprocess.CompletedProcess([], 0, "\n".join(["uevent", *targets]), "")
        name = path.rsplit("/", 1)[-1]
        assert path == DEVICE + "/" + name and name in targets
        assert (command, option) in (("readlink", "-f"), ("test", "-d"))
        if name == denied:
            return subprocess.CompletedProcess([], 1, "", "Permission denied")
        return subprocess.CompletedProcess([], 0, targets[name], "")
    return shell


class BindingTest(unittest.TestCase):
    def setUp(self):
        self.targets = {
            "of_node": "/sys/firmware/devicetree/base/soc/ufshc@624000",
            "driver": "/sys/bus/platform/drivers/ufshcd-qcom",
        }

    def test_absence(self):
        self.assertEqual(query_links(fixture(self.targets))["iommu_group"], {"state": "NOT-EXPORTED"})

    def test_exported_group_is_only_a_linux_group(self):
        target = "/sys/kernel/iommu_groups/8"
        self.targets["iommu_group"] = target
        self.assertEqual(query_links(fixture(self.targets))["iommu_group"],
                         {"state": "EXPORTED", "target": target, "linuxGroupNumber": 8})

    def test_access_denied(self):
        with self.assertRaisesRegex(RuntimeError, "unreadable"):
            query_links(fixture(self.targets, denied="driver"))
        with self.assertRaisesRegex(RuntimeError, "Cannot enumerate"):
            query_links(lambda *args: subprocess.CompletedProcess([], 1, "", "Permission denied"))

    def test_unexpected_target(self):
        self.targets["of_node"] = "/sys/firmware/devicetree/base/soc/usb"
        with self.assertRaisesRegex(ValueError, "disagree"):
            query_links(fixture(self.targets))


if __name__ == "__main__":
    unittest.main()

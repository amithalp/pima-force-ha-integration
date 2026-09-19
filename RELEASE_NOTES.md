# PIMA Force 1.21.1

This patch updates the Last triggered zone sensor after the panel supplies zone
names. A temporary value such as `Zone 6` becomes the configured name without
waiting for another alarm. The numeric zone ID remains in the `zone` attribute.

## Validation

The full local suite passes, including a regression test for names arriving
after the last triggered zone was first shown by number.

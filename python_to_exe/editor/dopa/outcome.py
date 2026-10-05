"""True result classes for Validate / F7 / F5 / F8 (dopagaki3.md §9.1). No Tk.

Celebrations may only follow these classes. "Success" for a conversion means
the parent Converter's own success event: every command exited 0 and the
expected output files exist. A send is confirmed only by the converter's
upload line: tsv-tas.py exits 0 even after printing "FTP error".
"""

SUCCESS = "success"                  # F5: local output generated.
SEND_CONFIRMED = "send_confirmed"    # F8: output generated and upload confirmed.
SEND_UNVERIFIED = "send_unverified"  # F8: output generated, upload not confirmed.
FAILED = "failed"

UPLOAD_CONFIRMED_LINE = "Script successfully uploaded"


def classify_conversion(succeeded, send, stdout=""):
    if not succeeded:
        return FAILED
    if not send:
        return SUCCESS
    confirmed = any(line.strip() == UPLOAD_CONFIRMED_LINE
                    for line in (stdout or "").splitlines())
    return SEND_CONFIRMED if confirmed else SEND_UNVERIFIED


def round_settles(outcome):
    """A round ends only when its goal is a fact: local output, or a confirmed send."""
    return outcome in (SUCCESS, SEND_CONFIRMED)


# RPKI aux functions
from . import log


def get_rpki_val_result(mgr, asn, network, netmask):
    try:
        result = mgr.validate(asn, network, netmask)
        if result.is_valid:
            return "VD"
        if result.is_invalid:
            if result.as_invalid:
                return "IA"
            if result.length_invalid:
                return "IL"
            return "IU"
        if result.not_found:
            return "NF"
        return "NA"
    except Exception:
        log.exception("exception")
        return "NA"

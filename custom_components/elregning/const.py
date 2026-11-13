"""Konstanter for Elregning."""

DOMAIN = "elregning"
STORAGE_KEY = "elregning.regninger"
STORAGE_VERSION = 1

CONF_ENERGY = "energy_entity"
CONF_COST = "cost_entity"

# Dage bag de seneste hele dage, det daglige gennemsnit til prognosen regnes over
AVERAGE_DAYS = 14
# Antal måneder bagud, der vises målt forbrug for
HISTORY_MONTHS = 6

SERVICE_ADD = "add_bill"
SERVICE_UPDATE = "update_bill"
SERVICE_DELETE = "delete_bill"

# Forsyninger, en regning kan være for. Kun el holdes op mod HA's måling.
UTILITIES = ("el", "gas")

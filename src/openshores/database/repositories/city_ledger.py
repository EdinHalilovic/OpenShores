
from __future__ import annotations


NATIVE_LEDGER_COLUMNS = {
    "bankBalance":      ("bank",            "+0x488 citizen/salary account"),
    "bankExSalary":     ("salaries_paid",   "+0x4c8 salaries paid out"),
    "bankInSalary":     ("salary_income",   "+0x500 net salary returned"),
    "bankInSales":      ("sales_income",    "+0x508 citizen sales revenue"),
    "bankExPurchases":  ("purchases_paid",  "+0x4b0 citizen purchases"),
    "bsCurrentBalance": ("govt",            "+0x518 government treasury"),
    "bsInIncomeTax":    ("govt_income_tax", "income tax collected"),
    "bsInSalesTax":     ("govt_sales_tax",  "sales tax collected"),
    "bsExTribute":      ("tribute_paid",    "+0x530 tribute sent"),
    "lastTribute":      ("last_tribute",    "+0x408 last tribute amount"),
}

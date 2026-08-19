# Data access, one file per aggregate (Company, Shipment, Document, ...). Repositories
# may import models/, never services/. Every query method must take a mandatory
# tenant-scope (company_id) parameter — see architecture doc Section 14.

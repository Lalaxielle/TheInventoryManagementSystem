"""Sample data used to seed the DEMO (SQLite) database.

The same content is mirrored in `database/seed.sql` for Supabase projects.
All dates are written relative to the authoring date so warranty states
(expired / expiring / active) are always varied.
"""

import config as _cfg  # project root (app.py adds it to sys.path)

ADMIN_USERNAME = _cfg.DEMO_ADMIN_USER
ADMIN_PASSWORD = _cfg.DEMO_ADMIN_PASSWORD
ADMIN_FULL_NAME = "System Administrator"

# asset_tag, model, brand, category, serial_no, assigned_to, location,
# status, condition, purchase_date, warranty_expiry, notes
EQUIPMENT = [
    ("IT-0001", "ThinkPad T14 Gen 3", "Lenovo", "Laptop", "PF3K8T21", "Juan Dela Cruz",
     "Rm 301 - Finance", "Assigned", "Good", "2024-03-15", "2027-03-15",
     "Issued with docking station."),
    ("IT-0002", "Latitude 5440", "Dell", "Laptop", "7HQ2LM3", "Maria Santos",
     "Rm 205 - HR", "Assigned", "Good", "2023-11-20", "2025-11-20",
     "Warranty expired - renew next budget cycle."),
    ("IT-0003", "MacBook Air M2", "Apple", "Laptop", "C02X45M8Q6L4", "Pedro Reyes",
     "Rm 108 - Marketing", "Assigned", "Good", "2024-01-30", "2028-01-30", ""),
    ("IT-0004", "UltraSharp U2422H", "Dell", "Monitor", "CN0X7T9", "",
     "Stock Room A", "Under Maintenance", "Fair", "2024-06-10", "2026-12-15",
     "HDMI port fault - with service center."),
    ("IT-0005", "EW2780", "BenQ", "Monitor", "ETX8K001", "Reception Desk",
     "Ground Floor - Lobby", "Assigned", "Fair", "2023-09-01", "2026-10-30",
     "Flickers on cold start."),
    ("IT-0006", "LaserJet Pro M404dn", "HP", "Printer", "VNC4R12345", "Admin Pool",
     "Rm 110 - Admin", "Assigned", "Good", "2024-02-05", "2026-02-05",
     "Shared network printer."),
    ("IT-0007", "OptiPlex 7010", "Dell", "Desktop", "4KJ8NP2", "Ana Cruz",
     "Rm 205 - HR", "Assigned", "Good", "2025-09-12", "2027-09-12", ""),
    ("IT-0008", "ProDesk 400 G9", "HP", "Desktop", "8CC1234ABC", "",
     "Stock Room A", "In Stock", "Good", "2025-03-01", "2028-03-01",
     "Spare unit for new hires."),
    ("IT-0009", "iPhone 14", "Apple", "Phone", "F17X9QLK", "Carlo Tan",
     "Field - Sales", "Assigned", "Good", "2023-12-08", "2025-12-08",
     "Company line: 0917-555-0134."),
    ("IT-0010", "Galaxy S23", "Samsung", "Phone", "R58W41", "",
     "Stock Room A", "Borrowed", "Good", "2024-08-22", "2026-11-05",
     "Loaner phone for events."),
    ("IT-0011", "PowerEdge R650", "Dell", "Server", "7YH2K03", "IT Ops",
     "Server Room", "Assigned", "Good", "2024-04-18", "2027-04-18",
     "Hosts ERP and file shares."),
    ("IT-0012", "UniFi U6 Pro", "Ubiquiti", "Network", "F49A2B1C", "",
     "Server Room", "In Stock", "Good", "2024-10-05", "2026-10-05",
     "Spare access point."),
    ("IT-0013", "Brio 500", "Logitech", "Peripheral", "2247LZ0", "",
     "Stock Room B", "Borrowed", "Good", "2025-01-20", "2027-01-20",
     "Conference room webcam."),
    ("IT-0014", "TS-464", "QNAP", "Storage", "QN8H47", "IT Ops",
     "Server Room", "Assigned", "Good", "2023-01-25", "2026-01-25",
     "Nightly backup target."),
    ("IT-0015", "Surface Pro 9", "Microsoft", "Tablet", "038972615", "IT Pool",
     "Rm 302 - IT Dept", "Under Maintenance", "Fair", "2024-05-30", "2026-12-01",
     "Battery swelling - repair in progress."),
    ("IT-0016", "Catalyst 9200", "Cisco", "Network", "FOC2508X1", "IT Ops",
     "Server Room", "Assigned", "Good", "2025-05-14", "2027-05-14",
     "Core switch, 3rd floor closet."),
    ("IT-0017", "ProBook 450 G10", "HP", "Laptop", "5CD3456XYZ", "",
     "Stock Room B", "Retired", "Damaged", "2022-07-10", "2025-07-10",
     "Motherboard failure - retired, awaiting disposal."),
]

# equipment_id (IT-####), mtype, description, scheduled_date, completed_date,
# status, technician, cost
MAINTENANCE = [
    ("IT-0015", "Repair", "Replace swollen battery and run full diagnostics",
     "2026-10-14", "", "In Progress", "Ramon Diaz", 0),
    ("IT-0004", "Repair", "Replace faulty HDMI port, unit with service center",
     "2026-10-10", "", "Scheduled", "IT Ops", 0),
    ("IT-0006", "Preventive", "Annual preventive maintenance and toner check",
     "2026-10-25", "", "Scheduled", "KPM Services", 3500),
    ("IT-0011", "Inspection", "Quarterly server health and dust cleanup",
     "2026-09-28", "2026-09-28", "Completed", "Ramon Diaz", 0),
]

# equipment_id (IT-####), borrower, department, purpose, borrowed_date, due_date,
# returned_date, status, notes
BORROWINGS = [
    ("IT-0010", "Marco Villanueva", "Marketing", "Client presentation - offsite",
     "2026-10-10", "2026-10-24", "", "Borrowed", ""),
    ("IT-0013", "Diana Reyes", "Sales", "Product demo kit",
     "2026-09-25", "2026-10-05", "", "Borrowed", "Reminder sent twice."),
    ("IT-0003", "Sofia Lim", "HR", "New hire orientation",
     "2026-09-15", "2026-09-22", "2026-09-20", "Returned", ""),
]

# action, entity, detail, created_at
ACTIVITY = [
    ("LOGIN", "session", "Signed in as admin", "2026-10-17 08:30:00"),
    ("MAINTENANCE", "IT-0015", "Repair started for Surface Pro 9", "2026-10-14 09:00:00"),
    ("CREATE", "IT-0017", "Registered ProBook 450 G10 (HP) and marked Retired",
     "2026-10-16 15:40:00"),
    ("UPDATE", "IT-0012", "Updated warranty expiry for UniFi U6 Pro",
     "2026-10-16 11:05:00"),
    ("BORROW", "IT-0010", "Galaxy S23 issued to Marco Villanueva (due 2026-10-24)",
     "2026-10-10 10:15:00"),
    ("MAINTENANCE", "IT-0004", "HDMI port repair scheduled for UltraSharp U2422H",
     "2026-10-08 14:20:00"),
    ("BORROW", "IT-0013", "Brio 500 issued to Diana Reyes (due 2026-10-05)",
     "2026-09-25 14:00:00"),
    ("MAINTENANCE", "IT-0011", "Inspection completed for PowerEdge R650",
     "2026-09-28 13:30:00"),
    ("RETURN", "IT-0003", "MacBook Air M2 returned by Sofia Lim",
     "2026-09-20 16:20:00"),
    ("CREATE", "IT-0001", "Registered ThinkPad T14 Gen 3 (Lenovo)", "2026-10-01 09:00:00"),
]

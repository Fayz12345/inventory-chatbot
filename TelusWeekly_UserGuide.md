# Telus Weekly Report — User Guide

## Getting Started

### Logging In

1. Open your browser and go to **http://3.96.54.81:5000**
2. Enter your username and password, then click **Sign In**
3. You'll land on the **Bridge Platform** home page with three options:
   - **Inventory Chatbot** — Ask questions about current inventory
   - **Ecommerce** — Pricing dashboard and marketplace listings
   - **Analytics** — Telus Weekly reports and pricing tools

---

## Running a Telus Weekly Report

1. From the home page, click **Analytics**
2. Click **Telus Weekly Report**
3. Enter the **ProjectTag** (e.g., `TW1626`)
   - Client Name is optional — leave it blank to include all clients, or type a client name to filter
4. Click **Generate Report**
5. The report will load in your browser with the full Repair & Resell breakdown

### What the Report Shows

**Summary Bar (top of page)**

- **Total Devices** — Number of devices in this project
- **Total Lot Value** — Combined best recovery value across all devices
- **Recommendation counts** — How many devices fall into each category (Sell After Repair, Sell As Is, etc.)
- **Unpriced Models** — If any device models are missing from the pricing master (see below)

**Report Table**

Each row is one device. The columns are:

| Column | What It Means |
|--------|---------------|
| ESN | Device serial number / IMEI |
| Make | Manufacturer (Apple, Samsung, Google, etc.) |
| Model | Full model name including storage (e.g., "iPhone 14 Pro Max 128 GB") |
| Memory | Device storage |
| Condition | Device state: Functional, Defective, FRP, or NYT (Not Yet Tested) |
| Fault 1 / 2 / 3 | Damage types found during assessment |
| QC Notes | Quality control notes |
| Unassessed Price | Starting price before grading (based on condition) |
| Received Grade | Grade assigned at intake (A, B, or C) |
| Assessed Price | Price based on the received grade |
| Repair Labour / Parts | Cost of repair work and parts |
| Total Repair Cost | Labour + Parts combined |
| Grade After Repair | Expected grade after repair |
| Price After Repair | What the device is worth after repair |
| Upside | Profit from repairing (Price After Repair minus costs). Only applies to Defective/FRP devices |
| Grade Improvement | Whether grade improvement was attempted (Yes/No) |
| Improvement Labour / Parts | Cost of grade improvement work |
| Total Improvement | Combined improvement costs |
| Grade After Improvement | Expected grade after improvement |
| Total Repair + Improvement | All repair and improvement costs combined |
| Price After Improvement | Value if grade is improved |
| Improvement Upside | Profit from improving grade. Only applies to Functional devices |
| **Recommendation** | What to do with this device (see below) |
| **Lot Value** | Best recovery value for this device |

### Recommendation Types

| Recommendation | Meaning |
|---------------|---------|
| **Sell After Repair** | Repairing this device is profitable — repair it, then sell at the higher grade price |
| **Sell As Is** | Repair costs exceed the price gain — sell the device in its current state |
| **Sell After Grade Improvement** | Improving the grade (e.g., B to A) is profitable — improve it, then sell |
| **Sell As Functional** | Grade improvement isn't profitable — sell at the current grade price |

### Unpriced Models Warning

If any device models in the report are not found in the pricing master, you'll see a red warning banner at the top listing the missing models. These devices will show $0 pricing.

To fix this:
1. Click the **Open Price Review** link in the warning banner
2. Add the missing model(s) with their prices
3. Go back and **re-run the report** — the prices will now calculate correctly

---

## Exporting to Excel

1. After generating a report, click the **Export to Excel** button
2. A `.xlsx` file will download with three sheets:
   - **Repair & Resell** — The full report table with all columns
   - **Models** — A summary of which models appeared and how many of each
   - **Summary** — Total devices, total lot value, and breakdowns by recommendation and condition

The file is named `TW_{ProjectTag}_{date}.xlsx` (e.g., `TW_TW1626_20260503.xlsx`).

---

## Price Review — Viewing and Editing Prices

The Price Review page lets you view and update the pricing master that the report uses for all calculations.

### Viewing Prices

1. From the home page, click **Analytics**
2. Click **Price Review**
3. You'll see all models with their current prices for each grade (A, B, C), Defective, FRP, and device type
4. Use the **search bar** at the top to filter by model name

### Editing Prices

1. Click into any price cell and type the new value
2. Changed cells turn **yellow** so you can see what you've modified
3. When you're done, click **Save Changes** — all your edits are saved at once
4. A confirmation message will appear when the save is successful

### Adding a New Model

1. Click the **+ Add Model** button at the top
2. A new row will appear — enter the model name, prices for each grade, and select the device type
3. Click **Add** to save the new model
4. The page will refresh with the new model in the list

### Device Types

| Type | Description |
|------|-------------|
| Phone | Standard mobile phone (default) |
| Tablet | Tablet device |
| Watch | Smartwatch |
| Modem | Network modem — these are priced at $0 for unassessed value |

---

## Tips

- **Run reports as needed** — there is no limit on how many times you can generate a report for the same ProjectTag
- **Check for unpriced models first** — if you see the red warning banner, add the missing models in Price Review before making business decisions based on the report
- **Price changes take effect immediately** — after saving in Price Review, the next report you run will use the updated prices
- **Use Excel export for sharing** — the downloaded file is ready to email or print without any formatting needed

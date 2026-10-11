# Data Dictionary

## Overview
This dataset is generated for Meridian Distribution and is stored in `data/business.duckdb`.
The data is seeded with a fixed random seed of `42` to make the patterns reproducible and to support later analysis and validation.

## Tables

### `regions`
| Column | Type | Description |
| --- | --- | --- |
| `region` | text | Distribution region. Values come from the app metadata: North, South, East, and West. |

### `products`
| Column | Type | Description |
| --- | --- | --- |
| `product_id` | text | Stable product identifier. |
| `product_name` | text | Display name of the product. |
| `category` | text | Product category from the dimension metadata. |
| `unit_price` | double | Unit list price used in revenue calculations. |
| `unit_cost` | double | Estimated per-unit cost used in margin calculations. |

### `customers`
| Column | Type | Description |
| --- | --- | --- |
| `customer_id` | text | Stable customer identifier. |
| `customer_name` | text | Human readable customer name. |
| `region` | text | Region the customer belongs to. |
| `segment` | text | Customer segment. Values include Enterprise, SMB, and Retail. |
| `signup_date` | date | Date the customer joined. |

### `orders`
| Column | Type | Description |
| --- | --- | --- |
| `order_id` | text | Unique order identifier. |
| `order_date` | date | Order placement date. |
| `customer_id` | text | Reference to the customer placing the order. |
| `region` | text | Customer region at the time of order. |
| `channel` | text | Sales channel: Online, Retail, or Partner. |
| `status` | text | Order status: completed, returned, or cancelled. |

### `order_items`
| Column | Type | Description |
| --- | --- | --- |
| `order_id` | text | Associated order. |
| `product_id` | text | Product sold in the order line. |
| `quantity` | integer | Number of units sold. |
| `unit_price` | double | Price used for the line item. |
| `discount_pct` | double | Discount applied to the line item as a decimal fraction. |
| `revenue` | double | Computed revenue for the line item. |
| `cost` | double | Computed product cost for the line item. |

### `inventory`
| Column | Type | Description |
| --- | --- | --- |
| `snapshot_date` | date | Weekly inventory snapshot date. |
| `region` | text | Region for which the inventory snapshot applies. |
| `product_id` | text | Product tracked in the snapshot. |
| `stock_on_hand` | integer | Units currently on hand. |
| `reorder_level` | integer | Replenishment threshold for the product. |

### `expenses`
| Column | Type | Description |
| --- | --- | --- |
| `month` | date | Month for the expense record. |
| `region` | text | Region the expense belongs to. |
| `expense_type` | text | Expense category: Logistics, Payroll, Marketing, or Facilities. |
| `amount` | double | Monthly expense amount. |

### `targets`
| Column | Type | Description |
| --- | --- | --- |
| `month` | date | Month for the sales target record. |
| `region` | text | Regional target geography. |
| `category` | text | Product category for the target. |
| `revenue_target` | double | Monthly revenue target value. |

## Planted story definitions

### Story 1: South revenue drop in the latest calendar quarter
- Period used: the quarter ending on the fixed as-of date, 2026-07-01 through 2026-09-30.
- Region: South
- Comparison period: previous calendar quarter, 2026-04-01 through 2026-06-30.
- Expected pattern: South revenue is approximately 20% lower than the previous quarter.
- Main contributors: Beverages category drops by about 35% in South and the Partner channel drops by about 40% in South.
- Other regions are kept near normal and are not the primary source of the decline.

### Story 2: Household promotion spike in the last 30 days
- Period used: the 30 days ending on the fixed as-of date, 2026-09-01 through 2026-09-30.
- Category: Household
- Product: the first Household product in the generated catalog is promoted with a larger discount and a roughly 60% higher order volume.
- Channel impact: this is visible in the order items during the last 30 days.

### Story 3: West inventory warning
- Period used: most recent inventory snapshots.
- Region: West
- Condition: one Household product is intentionally kept below its reorder level in the newest snapshots.
- This is meant to simulate an inventory risk signal for operational review.

### Story 4: East marketing expense bump
- Period used: the latest quarter ending on the fixed as-of date, 2026-07-01 through 2026-09-30.
- Region: East
- Expense type: Marketing
- Condition: Marketing spend rises noticeably for the East region during that quarter.

## Exact periods used in generation
Generation is anchored to 2026-09-30 (or `APP_AS_OF_DATE` when explicitly overridden).
The generation window starts on 2024-09-30 and ends on the as-of date. The planted
quarter stories use the quarter containing the as-of date and the preceding quarter;
the promotion window is the 30 calendar days ending on the as-of date.

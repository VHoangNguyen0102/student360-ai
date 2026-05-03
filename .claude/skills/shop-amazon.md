# Skill: Shop Amazon

A reusable skill template for purchasing items on Amazon. This demonstrates the skill file format — copy and adapt for other task automations.

---

## Trigger

Use this skill when asked to:
- "Buy X on Amazon"
- "Order X from Amazon"
- "Find and purchase X"

---

## Inputs

| Parameter | Type | Required | Description |
|---|---|---|---|
| `item_description` | string | Yes | What to search for (e.g., "USB-C hub 7-port") |
| `max_price_usd` | number | No | Maximum price in USD (default: no limit) |
| `prime_only` | boolean | No | Only show Prime-eligible items (default: true) |
| `quantity` | number | No | How many to order (default: 1) |

---

## Steps

### 1. Search for the Item
- Open `https://www.amazon.com/s?k={item_description}`
- Filter results by Prime if `prime_only=true`
- Filter by price if `max_price_usd` is set

### 2. Evaluate Top Results
For each of the top 3 results, check:
- Price (is it within budget?)
- Ratings (>= 4 stars preferred)
- Review count (>= 100 reviews preferred)
- Delivery estimate (when will it arrive?)
- Seller (Amazon.com preferred over third-party)

### 3. Select the Best Option
Choose the item that best balances: price, ratings, review volume, and delivery speed.

### 4. Present Selection for Approval
Before adding to cart, show the user:
```
Item: {title}
Price: ${price}
Rating: {stars}/5 ({review_count} reviews)
Delivery: {delivery_estimate}
URL: {product_url}

Proceed with purchase? (yes/no)
```

### 5. Complete Purchase (only after approval)
- Add item to cart
- Verify shipping address matches user's default
- Apply any available promo codes
- Place order
- Confirm order number

---

## Output

```
Order placed successfully.
- Order ID: {order_id}
- Item: {title}
- Price paid: ${price}
- Estimated delivery: {delivery_date}
```

---

## Notes

- Always request explicit user approval before completing a purchase (Step 4)
- If multiple items have identical ratings, prefer the one with more reviews
- If no item meets the criteria, report back and ask for adjusted requirements
- Do not save or log credit card information

# 🎓 College Budget Tracker

A personal monthly budget tracker designed for college students. Track spending across categories, set monthly budgets, and visualize budget variance — all in a single-page app with no dependencies.

## Features

- **11 College-Focused Categories**: Housing, Food, Tuition, Textbooks, Transportation, Entertainment, Subscriptions, Personal Care, Clothing, Savings, Miscellaneous
- **Monthly Budget Setting**: Set custom budget limits for each category per month
- **Expense Tracking**: Add, view, and delete expenses with descriptions and dates
- **Budget Variance**: See at a glance how you're tracking against your budget — per category and overall
- **Visual Charts**: Doughnut chart for spending breakdown, bar chart for budget vs. actual comparison
- **Progress Bars**: Color-coded progress indicators per category (turns red when over budget)
- **Month Navigation**: Browse between months to review past spending or plan ahead
- **Local Storage Persistence**: All data is saved in your browser — no server or account needed
- **Responsive Design**: Works on desktop, tablet, and mobile

## Getting Started

Simply open `index.html` in your browser:

```bash
# Option 1: Direct file open
open index.html

# Option 2: Local server (for development)
python3 -m http.server 8080 --directory .
# Then visit http://localhost:8080
```

## Usage

1. **Set Your Budget**: Click the ✏️ button (bottom-right) to set monthly budget amounts per category
2. **Add Expenses**: Click "+ Add Expense" to log a purchase with category, description, amount, and date
3. **Review Variance**: Each category shows a variance badge (green = under budget, red = over budget)
4. **Navigate Months**: Use the ← → arrows in the header to switch between months
5. **Delete Expenses**: Click the ✕ button next to any transaction to remove it

## Tech Stack

- Vanilla HTML, CSS, JavaScript
- Canvas 2D API for charts (zero dependencies)
- localStorage for data persistence

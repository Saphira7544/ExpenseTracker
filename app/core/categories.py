# This is now the ONLY place you edit to add/remove/rename a category.
# Everything else (the API, the rule-based UI dropdowns, the OpenAI
# categorizer, badges and chart colours) reads from here.

CATEGORIES = [
    "Salary",
    "Investments",
    "Groceries",
    "Restaurants/Bars",
    "Transport",
    "Housing",
    "Rents",
    "Health",
    "Subscriptions",
    "Transfers",
    "Internal",          # between your own accounts / currency exchanges: ignored by the dashboards
    "Shopping",
    "Entertainment",
    "Education/Work",
    "Travel",
    "Sports",
    "Other",
]

# One fixed colour per category, used by every badge and chart, so a category
# looks the same everywhere no matter how it ranks in a given month.
# Hues follow meaning; lightness/chroma were tuned (OKLab) to keep the
# colours as far apart as 15 meaningful hues allow. Charts always show the
# category name too (legend/table), never colour alone.
CATEGORY_COLORS = {
    "Salary": "#017e45",            # green: money coming in
    "Investments": "#7602c3",       # violet: same as "Invested" on the dashboard
    "Groceries": "#6da905",         # leaf green: fresh food
    "Restaurants/Bars": "#fd7328",  # orange: food & drinks
    "Transport": "#1650fc",         # blue: transit
    "Housing": "#a7770a",           # ochre: home
    "Rents": "#8b3b17",             # brick: the big fixed home cost
    "Health": "#cf294a",            # red: medical
    "Subscriptions": "#3a4e9d",     # indigo: recurring digital
    "Transfers": "#1482ca",         # steel blue: money between people
    "Shopping": "#eb74bb",          # pink
    "Entertainment": "#9e4ea1",     # purple-magenta: fun
    "Education/Work": "#01a698",    # teal: learning & work
    "Travel": "#10c2f9",            # sky: sky and sea
    "Sports": "#d8af19",            # yellow: energy
    # Neutrals: not "real" spending categories
    "Internal": "#cbd5e1",          # light slate: ignored by the dashboards
    "Other": "#6b7280",             # grey: catch-all (also the "everything else" bucket in charts)
    "Uncategorized": "#9ca3af",     # light grey: not categorised yet
    "Split": "#334155",             # dark slate: a transaction split into parts
}

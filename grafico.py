import json
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

# Load your file
with open('tokens_by_page_bom.json', 'r') as f:
    domain_tokens = json.load(f)

# Convert to pandas DataFrame
df = pd.DataFrame(list(domain_tokens.items()), columns=['domain', 'tokens'])

# Sort by tokens descending
df = df.sort_values(by='tokens', ascending=False).reset_index(drop=True)

# === YOU PASS THE BINS MANUALLY HERE ===
# Example: you can change these values however you want
bins = [0, 100, 500, 1_000, 2_000, 3_000, 5_000, 10_000, 50_000, np.inf]

# Create labels based on your bins
labels = [f'{int(bins[i]):,}-{int(bins[i+1]-1):,}' if np.isfinite(bins[i+1]) 
          else f'{int(bins[i]):,}+' for i in range(len(bins)-1)]

# Assign bins
df['token_range'] = pd.cut(df['tokens'], bins=bins, labels=labels, include_lowest=True)

# Group by token range and count pages
grouped = df['token_range'].value_counts().sort_index().reset_index()
grouped.columns = ['token_range', 'num_pages']

# Calculate percentages
total_pages = grouped['num_pages'].sum()
grouped['percentage'] = (grouped['num_pages'] / total_pages) * 100

# Plot
plt.figure(figsize=(10, 7))
bars = plt.bar(grouped['token_range'], grouped['percentage'], color='skyblue')

# Add percentage labels on top
for bar, pct in zip(bars, grouped['percentage']):
    height = bar.get_height()
    plt.text(bar.get_x() + bar.get_width()/2, height + 0.5, f'{pct:.1f}%', ha='center', va='bottom', fontsize=8)

plt.title('Percentage of Pages by # Token Ranges')
plt.xlabel('Token Ranges (Tokens per Page)')
plt.ylabel('Percentage of Pages (%)')
plt.xticks(rotation=45, ha='right')
plt.tight_layout()

# Save figure
plt.savefig('pages_percentage_by_token_ranges_custom.png', dpi=300)
print("Chart saved as 'pages_percentage_by_token_ranges_custom.png'.")

with open('domain_count_bom.json', 'r') as f:
    domain_counts = json.load(f)

# Convert to pandas DataFrame
df = pd.DataFrame(list(domain_counts.items()), columns=['domain', 'num_subpages'])

# Sort by number of subpages descending
df = df.sort_values(by='num_subpages', ascending=False).reset_index(drop=True)

# Select the top 10 domains
top_10_domains = df.head(10)

# Print the result
print(top_10_domains)

total_domains = len(df)

# Filter domains with more than 676 subpages
domains_above_676 = df[df['num_subpages'] > 676]

# Calculate the number of such domains
num_domains_above_676 = len(domains_above_676)

# Calculate the percentage
percentage = (num_domains_above_676 / total_domains) * 100

# Print the result
print(f"Percentage of domains with more than 676 subpages: {percentage:.2f}%")
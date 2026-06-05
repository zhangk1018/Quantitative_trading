---
name: "agent-browser"
description: "Provides browser automation CLI for AI Agent, supporting page navigation, form filling, button clicking, data scraping, and web application testing. Invoke when user needs browser automation or web testing."
---

# Agent Browser

This skill provides browser automation capabilities for AI Agents, enabling automated interactions with web applications.

## Core Features

### 1. Page Navigation
- Navigate to URLs
- Forward/backward navigation
- Refresh pages
- Handle redirects

### 2. Form Handling
- Fill input fields
- Select dropdown options
- Check checkboxes and radio buttons
- Submit forms

### 3. Element Interaction
- Click buttons and links
- Hover over elements
- Extract text and attributes
- Wait for elements to appear

### 4. Data Scraping
- Extract structured data from pages
- Handle pagination
- Parse tables and lists
- Export data to various formats

### 5. Web Testing
- Validate page content
- Test user flows
- Check for broken links
- Performance monitoring

## Usage Examples

### Example 1: Basic Navigation
```python
from browser_automation import Browser

browser = Browser()
browser.navigate("https://example.com")
title = browser.get_title()
print(f"Page title: {title}")
browser.close()
```

### Example 2: Form Submission
```python
browser = Browser()
browser.navigate("https://example.com/login")
browser.fill_input("#username", "test_user")
browser.fill_input("#password", "secret123")
browser.click_button("Login")
browser.wait_for_redirect()
browser.close()
```

### Example 3: Data Scraping
```python
browser = Browser()
browser.navigate("https://example.com/products")
products = browser.extract_table("#product-table")
for product in products:
    print(f"{product['name']}: ${product['price']}")
browser.close()
```

## Best Practices

1. **Use Explicit Waits**: Always wait for elements before interacting
2. **Handle Dynamic Content**: Account for AJAX-loaded content
3. **Use Selectors Wisely**: Prefer IDs and data attributes over CSS classes
4. **Clean Up**: Always close the browser after completing tasks
5. **Error Handling**: Implement try-catch blocks for robust automation

## Common Use Cases

- Automated testing of web applications
- Web scraping and data extraction
- Automated form filling
- UI regression testing
- Performance monitoring

## Checklist

- [ ] Browser instance is properly initialized
- [ ] Elements are located using reliable selectors
- [ ] Waits are implemented for dynamic content
- [ ] Browser is closed after task completion
- [ ] Error handling is in place
- [ ] Screenshots are captured for debugging

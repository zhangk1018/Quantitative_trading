---
name: "electron"
description: "Automates Electron desktop applications (VS Code, Slack, Discord, etc.) using Chrome DevTools Protocol and agent-browser. Invoke when automating desktop applications or testing Electron apps."
---

# Electron Automation

This skill provides automation capabilities for Electron-based desktop applications using Chrome DevTools Protocol.

## Core Features

### 1. Application Control
- Launch and close Electron apps
- Manage application windows
- Handle application lifecycle

### 2. UI Interaction
- Click buttons and menu items
- Fill forms and input fields
- Navigate through menus and dialogs

### 3. Data Extraction
- Extract content from windows
- Capture screenshots
- Access application state

### 4. Testing Support
- Automated UI testing
- Regression testing
- Performance monitoring

## Supported Applications

- VS Code
- Slack
- Discord
- Atom
- Postman
- And other Electron-based apps

## Usage Examples

### Example 1: Launch Application
```python
from electron_automation import ElectronAutomator

automator = ElectronAutomator()
automator.launch("/Applications/Visual Studio Code.app")
automator.wait_for_window()
```

### Example 2: Menu Interaction
```python
automator.click_menu("File", "New File")
automator.type_text("Hello World")
automator.click_menu("File", "Save")
```

### Example 3: Capture Screenshot
```python
screenshot = automator.capture_screenshot()
screenshot.save("vscode_screenshot.png")
```

## Best Practices

1. **Identify Target App**: Know the exact application path and name
2. **Wait for Ready**: Allow time for application to launch
3. **Handle Dialogs**: Account for modal dialogs and prompts
4. **Clean Up**: Close applications after testing
5. **Error Handling**: Implement proper exception handling

## Checklist

- [ ] Application path is correctly specified
- [ ] Application is running and responsive
- [ ] UI elements are accessible
- [ ] Actions are performed in correct order
- [ ] Cleanup is performed after testing
- [ ] Errors are properly handled
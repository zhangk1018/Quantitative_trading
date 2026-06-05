---
name: "test-driven-development"
description: "Defines clear implementation plans for feature development or bug fixes before writing code. Invoke when implementing new features or fixing bugs to ensure test coverage."
---

# Test-Driven Development

This skill guides the test-driven development approach for building quality software.

## TDD Process

### 1. Red Phase
- Write a failing test
- Define expected behavior
- Test should fail initially

### 2. Green Phase
- Implement minimal code to pass the test
- Focus on making the test pass
- Keep implementation simple

### 3. Refactor Phase
- Improve code quality
- Remove duplication
- Maintain test coverage

## Test Types

### Unit Tests
- Test individual functions/methods
- Isolate components
- Fast execution

### Integration Tests
- Test interactions between components
- Validate data flow
- Verify interfaces

### Acceptance Tests
- Test end-to-end scenarios
- Validate user workflows
- Business requirements

## Best Practices

1. **Write Tests First**: Tests define requirements
2. **Keep Tests Small**: Focus on one behavior at a time
3. **Test Boundary Cases**: Edge conditions matter
4. **Maintain Test Coverage**: Aim for high coverage
5. **Fast Feedback**: Tests should run quickly
6. **Refactor Regularly**: Keep code clean

## Testing Framework Guidelines

### Python
- pytest for unit testing
- unittest for standard library
- pytest-cov for coverage

### JavaScript/TypeScript
- Jest for unit testing
- Cypress for E2E testing
- React Testing Library for components

## Checklist

- [ ] Test is written before implementation
- [ ] Test covers expected behavior
- [ ] Test fails before implementation
- [ ] Implementation passes the test
- [ ] Code is refactored for quality
- [ ] All tests pass

## Output Deliverables

- Test suite
- Implementation code
- Test coverage report
- Refactored codebase
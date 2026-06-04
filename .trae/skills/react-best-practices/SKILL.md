---
name: "react-best-practices"
description: "Provides React/Next.js optimization guidelines, code standards, and best practices. Invoke when developing React components, optimizing performance, or ensuring code quality."
---

# React Best Practices

This skill provides comprehensive React/Next.js development guidelines and best practices to ensure high-quality, maintainable, and performant code.

## Core Principles

### 1. Component Design
- **Single Responsibility**: Each component should do one thing and do it well
- **Reusability**: Design components to be reusable across the application
- **Separation of Concerns**: Keep presentation logic separate from business logic

### 2. State Management
- Use React hooks (`useState`, `useEffect`) for local state
- Consider context or external libraries (Zustand, Redux) for global state
- Keep state minimal and derived values computed

### 3. Performance Optimization
- Use `React.memo` for expensive components
- Implement `useMemo` and `useCallback` for computationally heavy operations
- Virtualize long lists with libraries like `react-window` or `react-virtualized`
- Code-split with `React.lazy` and `Suspense`

### 4. Type Safety
- Use TypeScript for all React projects
- Define proper interfaces for props and state
- Leverage TypeScript's strict mode for better type checking

### 5. Hooks Best Practices
- Call hooks at the top level, not inside loops or conditions
- Custom hooks should start with `use` prefix
- Keep hooks small and focused

### 6. Data Fetching
- Use React Query or SWR for server state management
- Handle loading and error states properly
- Implement caching strategies

### 7. Styling
- Prefer CSS-in-JS or Tailwind CSS for styling
- Use theme providers for consistent design tokens
- Avoid inline styles for complex styling

### 8. Testing
- Write unit tests for components and hooks
- Use React Testing Library for component testing
- Mock external dependencies in tests

## Usage Examples

### Example 1: Optimizing a Component
```tsx
// Before - unnecessary re-renders
const ExpensiveComponent = ({ data }) => {
  const processed = heavyComputation(data);
  return <div>{processed}</div>;
};

// After - optimized with useMemo
const ExpensiveComponent = ({ data }) => {
  const processed = useMemo(() => heavyComputation(data), [data]);
  return <div>{processed}</div>;
};
```

### Example 2: Custom Hook
```tsx
// Custom hook for data fetching
const useFetch = <T>(url: string) => {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    fetch(url)
      .then(res => res.json())
      .then(setData)
      .catch(setError)
      .finally(() => setLoading(false));
  }, [url]);

  return { data, loading, error };
};
```

### Example 3: Memoized Component
```tsx
interface UserCardProps {
  user: User;
  onSelect: (id: string) => void;
}

// Memoize component to prevent unnecessary re-renders
const UserCard = React.memo<UserCardProps>(({ user, onSelect }) => {
  return (
    <div onClick={() => onSelect(user.id)}>
      <h3>{user.name}</h3>
      <p>{user.email}</p>
    </div>
  );
});
```

## Checklist

- [ ] Components follow single responsibility principle
- [ ] Props are properly typed with TypeScript
- [ ] Expensive computations use `useMemo`
- [ ] Event handlers use `useCallback` when needed
- [ ] Components are memoized when appropriate
- [ ] State is kept at the minimal required level
- [ ] Hooks are called at the top level
- [ ] Error boundaries are implemented where needed
- [ ] Loading states are handled properly
- [ ] Tests are written for critical components

## Common Anti-Patterns to Avoid

1. **Prop Drilling**: Instead of passing props through multiple levels, use Context or state management
2. **Overusing useState**: Derived values should be computed, not stored as state
3. **Ignoring TypeScript**: Always leverage TypeScript for type safety
4. **Monolithic Components**: Break large components into smaller, focused ones
5. **Uncontrolled Side Effects**: Always clean up effects in `useEffect`
6. **Inline Functions in Props**: Use `useCallback` or move functions outside the component

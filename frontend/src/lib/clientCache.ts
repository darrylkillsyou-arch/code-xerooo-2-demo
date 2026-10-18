/**
 * Lightweight in-memory TTL cache for the CODE XERO frontend.
 *
 * Avoids redundant API round-trips when the user navigates between pages.
 * Cache is scoped to the browser tab session — cleared on hard refresh.
 *
 * No external dependencies. No paid services.
 */

interface CacheEntry<T> {
  value: T;
  expiresAt: number; // Date.now() ms
}

class ClientCache {
  private store = new Map<string, CacheEntry<unknown>>();

  get<T>(key: string): T | null {
    const entry = this.store.get(key) as CacheEntry<T> | undefined;
    if (!entry) return null;
    if (Date.now() > entry.expiresAt) {
      this.store.delete(key);
      return null;
    }
    return entry.value;
  }

  set<T>(key: string, value: T, ttlMs: number): void {
    this.store.set(key, { value, expiresAt: Date.now() + ttlMs });
  }

  delete(key: string): void {
    this.store.delete(key);
  }

  clearPrefix(prefix: string): void {
    for (const key of this.store.keys()) {
      if (key.startsWith(prefix)) this.store.delete(key);
    }
  }

  has(key: string): boolean {
    return this.get(key) !== null;
  }
}

// Module-level singleton — shared across all pages within the same browser tab
export const clientCache = new ClientCache();

// TTL constants (milliseconds)
export const TTL = {
  CREATORS: 5 * 60 * 1000,       // 5 minutes
  CREATOR_DETAIL: 5 * 60 * 1000, // 5 minutes
  COMMUNITY: 60 * 1000,           // 60 seconds
  LEADERBOARD: 5 * 60 * 1000,    // 5 minutes
  PROPOSALS: 30 * 1000,           // 30 seconds (user data, shorter TTL)
  WORKSPACES: 30 * 1000,          // 30 seconds (user data, shorter TTL)
} as const;

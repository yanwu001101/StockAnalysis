package com.stock.service;

public final class DataTimeHolder {
    private static final ThreadLocal<Long> HOLDER = new ThreadLocal<>();

    private DataTimeHolder() {}

    public static void recordOldest(long ms) {
        Long existing = HOLDER.get();
        if (existing == null || ms < existing) {
            HOLDER.set(ms);
        }
    }

    public static Long getAndClear() {
        Long v = HOLDER.get();
        HOLDER.remove();
        return v;
    }

    public static void clear() {
        HOLDER.remove();
    }
}

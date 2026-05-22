package com.stock.service;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@AllArgsConstructor
@NoArgsConstructor
public class CachedEntry {
    private Object payload;
    private long writtenAt;
}

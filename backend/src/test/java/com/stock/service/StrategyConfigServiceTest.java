package com.stock.service;

import com.stock.exception.BusinessException;
import org.junit.jupiter.api.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;

class StrategyConfigServiceTest {
    private Map<String, Object> body(double weight) {
        return new HashMap<>(Map.of("version", 3, "config", Map.of("quality_factor", Map.of("weight", weight, "enabled", true)), "presets", List.of()));
    }
    @Test void zeroIsValidAndNaNIsRejected() {
        assertNotNull(StrategyConfigService.normalize(body(0)));
        for (double invalid : new double[]{-1, Double.NaN, Double.POSITIVE_INFINITY, 1001})
            assertThrows(BusinessException.class, () -> StrategyConfigService.normalize(body(invalid)));
    }
    @Test void duplicatePresetNamesAreRejected() {
        var body = body(10);
        var preset = Map.of("name", "test", "config", body.get("config"));
        body.put("presets", List.of(preset, preset));
        assertThrows(BusinessException.class, () -> StrategyConfigService.normalize(body));
    }
    @Test void staleRevisionIsConflictAndCannotOverwrite() {
        JdbcTemplate jdbc = mock(JdbcTemplate.class);
        var service = new StrategyConfigService(jdbc);
        var e = assertThrows(BusinessException.class, () -> service.save(42L, body(10)));
        assertEquals(409, e.getCode());
        verify(jdbc).update(startsWith("UPDATE"), anyString(), eq(42L), eq(3L));
    }
    @Test void savesExactOwnedRevision() {
        JdbcTemplate jdbc = mock(JdbcTemplate.class);
        when(jdbc.update(anyString(), anyString(), eq(42L), eq(3L))).thenReturn(1);
        var result = new StrategyConfigService(jdbc).save(42L, body(10));
        assertEquals(4L, result.get("version"));
    }
}

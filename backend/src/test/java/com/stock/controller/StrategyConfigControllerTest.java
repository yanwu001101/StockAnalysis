package com.stock.controller;

import com.stock.exception.BusinessException;
import com.stock.service.StrategyConfigService;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import java.util.Map;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class StrategyConfigControllerTest {
    @Test void ownershipComesFromAuthenticatedRequestNotPayload() {
        var service = mock(StrategyConfigService.class);
        var controller = new StrategyConfigController(service);
        var request = new MockHttpServletRequest(); request.setAttribute("userId", 7L);
        Map<String, Object> body = Map.of("userId", 99, "version", 0);
        controller.put(body, request);
        verify(service).save(7L, body);
    }
    @Test void anonymousRequestsFailBeforeAccessingStorage() {
        var service = mock(StrategyConfigService.class);
        var controller = new StrategyConfigController(service);
        assertThrows(BusinessException.class, () -> controller.get(new MockHttpServletRequest()));
        verifyNoInteractions(service);
    }
}

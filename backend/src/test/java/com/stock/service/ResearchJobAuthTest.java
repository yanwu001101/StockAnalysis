package com.stock.service;

import com.alibaba.fastjson2.JSONObject;
import com.stock.exception.BusinessException;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.Arguments;
import org.junit.jupiter.params.provider.MethodSource;
import org.junit.jupiter.params.provider.NullAndEmptySource;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestTemplate;

import java.nio.charset.StandardCharsets;
import java.util.stream.Stream;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.*;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

class ResearchJobAuthTest {
    static final String SECRET = "test-only-research-secret-0123456789abcdef";
    static final long NOW = 1_700_000_000;
    static final String PATH = "/api/async/alphalab-backtest";

    static Stream<Arguments> vectors() {
        // Identical constants also live in Python test_research_auth.py.
        return Stream.of(
                Arguments.of("POST", PATH, "{\"expression\":\"rank(close)\",\"top_n\":5}",
                        "5aaeb70038a5e0e51cc1a402a5496e6e399f28b55a328cb6bc93fb345c60aba3"),
                Arguments.of("POST", PATH, "{\"expression\":\"rank(close)\",\"label\":\"中文策略\"}",
                        "20099cdacee0da5ce51e8656869218b16d03f572de60fdfbe439da3d24bc8239"),
                Arguments.of("GET", "/api/async/jobs/RJ_20261012_0123456789abcdef0123456789abcdef", "",
                        "8971f2e05b890ddf45b8a21453028a27d652e86973d95a26e9b06a0b1a9f2b0f")
        );
    }

    @ParameterizedTest @MethodSource("vectors")
    void fixedCrossLanguageVectors(String method, String path, String body, String expected) {
        assertEquals(expected, ResearchJobAuth.signature(SECRET, 42, NOW, method, path, body.getBytes(StandardCharsets.UTF_8)));
    }

    @ParameterizedTest @NullAndEmptySource
    @ValueSource(strings = {"short", "                                ", "StockScreenerSecretKey2024MustBe256BitsLong!!", " StockScreenerSecretKey2024MustBe256BitsLong!!\n"})
    void invalidConfigurationFailsClosedWithoutReturningTheSecret(String secret) {
        BusinessException failure = assertThrows(BusinessException.class,
                () -> ResearchJobAuth.signature(secret, 42, NOW, "GET", PATH, new byte[0]));
        assertEquals(503, failure.getCode());
        assertFalse(failure.getMessage().contains("StockScreenerSecretKey2024"));
    }

    @ParameterizedTest @ValueSource(longs = {0, -1})
    void invalidOwnerIsNeverSigned(long owner) {
        assertEquals(401, assertThrows(BusinessException.class,
                () -> ResearchJobAuth.signature(SECRET, owner, NOW, "GET", PATH, new byte[0])).getCode());
    }

    @Test void oversizedBodyIsRejected() {
        assertEquals(413, assertThrows(BusinessException.class,
                () -> ResearchJobAuth.signature(SECRET, 42, NOW, "POST", PATH,
                        new byte[ResearchJobAuth.MAX_BODY_BYTES + 1])).getCode());
    }

    @SuppressWarnings("unchecked")
    private DataService service(RestTemplate rest) {
        DataService service = new DataService(rest, mock(RedisTemplate.class));
        ReflectionTestUtils.setField(service, "dataServiceUrl", "http://data-service:5001");
        ReflectionTestUtils.setField(service, "researchSigningSecret", SECRET);
        return service;
    }

    @Test void signsExactlyTheUtf8BytesActuallySentByRestTemplate() {
        RestTemplate rest = new RestTemplate();
        MockRestServiceServer server = MockRestServiceServer.createServer(rest);
        JSONObject payload = new JSONObject();
        payload.put("expression", "rank(close)"); payload.put("label", "中文策略"); payload.put("zero", 0);
        byte[] raw = payload.toJSONString().getBytes(StandardCharsets.UTF_8);
        server.expect(requestTo("http://data-service:5001" + PATH))
                .andExpect(method(HttpMethod.POST)).andExpect(content().bytes(raw))
                .andExpect(request -> {
                    var headers = request.getHeaders();
                    assertEquals("42", headers.getFirst(ResearchJobAuth.OWNER_HEADER));
                    assertEquals(StandardCharsets.UTF_8, headers.getContentType().getCharset());
                    long timestamp = Long.parseLong(headers.getFirst(ResearchJobAuth.TIME_HEADER));
                    assertEquals(ResearchJobAuth.signature(SECRET, 42, timestamp, "POST", PATH, raw),
                            headers.getFirst(ResearchJobAuth.SIGNATURE_HEADER));
                }).andRespond(withSuccess("{\"job_id\":\"fixture\",\"status\":\"QUEUED\"}", MediaType.APPLICATION_JSON));
        assertEquals("fixture", service(rest).submitResearchJob(PATH, payload, 42).getString("job_id"));
        server.verify();
    }

    @Test void getSignatureUsesAnEmptyBodyAndAuthenticatedOwner() {
        RestTemplate rest = new RestTemplate();
        MockRestServiceServer server = MockRestServiceServer.createServer(rest);
        String path = "/api/async/jobs/fixture";
        server.expect(requestTo("http://data-service:5001" + path)).andExpect(method(HttpMethod.GET))
                .andExpect(content().bytes(new byte[0])).andExpect(request -> {
                    var headers = request.getHeaders();
                    long timestamp = Long.parseLong(headers.getFirst(ResearchJobAuth.TIME_HEADER));
                    assertEquals("7", headers.getFirst(ResearchJobAuth.OWNER_HEADER));
                    assertEquals(ResearchJobAuth.signature(SECRET, 7, timestamp, "GET", path, new byte[0]),
                            headers.getFirst(ResearchJobAuth.SIGNATURE_HEADER));
                }).andRespond(withSuccess("{\"status\":\"QUEUED\"}", MediaType.APPLICATION_JSON));
        assertEquals("QUEUED", service(rest).getResearchJob("fixture", 7).getString("status"));
        server.verify();
    }
}

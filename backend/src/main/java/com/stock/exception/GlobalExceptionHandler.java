package com.stock.exception;

import com.stock.model.dto.ApiResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.HttpRequestMethodNotSupportedException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.client.HttpStatusCodeException;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;

@RestControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    // ---- Caller-safe (4xx) ------------------------------------------------

    @ExceptionHandler(BusinessException.class)
    public ResponseEntity<ApiResponse<?>> handleBusiness(BusinessException e) {
        // Already user-facing — pass message through, no stack trace in log
        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
                .body(ApiResponse.error(e.getCode(), e.getMessage()));
    }

    @ExceptionHandler({
            MethodArgumentNotValidException.class,
            MissingServletRequestParameterException.class,
            MethodArgumentTypeMismatchException.class,
            IllegalArgumentException.class,
    })
    public ResponseEntity<ApiResponse<?>> handleBadRequest(Exception e) {
        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
                .body(ApiResponse.error(400, "请求参数错误: " + e.getMessage()));
    }

    @ExceptionHandler(HttpRequestMethodNotSupportedException.class)
    public ResponseEntity<ApiResponse<?>> handleMethodNotAllowed(HttpRequestMethodNotSupportedException e) {
        return ResponseEntity.status(HttpStatus.METHOD_NOT_ALLOWED)
                .body(ApiResponse.error(405, "不支持的请求方法: " + e.getMethod()));
    }

    // ---- Downstream (data-service / akshare) -----------------------------

    @ExceptionHandler(ResourceAccessException.class)
    public ResponseEntity<ApiResponse<?>> handleDownstreamUnreachable(ResourceAccessException e) {
        log.warn("data-service unreachable: {}", e.getMessage());
        return ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                .body(ApiResponse.error(502, "数据服务暂时不可用,请稍后重试"));
    }

    @ExceptionHandler(HttpStatusCodeException.class)
    public ResponseEntity<ApiResponse<?>> handleDownstreamError(HttpStatusCodeException e) {
        // 4xx/5xx from data-service. Body is JSON, but log defensively.
        log.warn("data-service returned {}: {}", e.getStatusCode(), e.getStatusText());
        return ResponseEntity.status(HttpStatus.BAD_GATEWAY)
                .body(ApiResponse.error(502, "数据服务错误"));
    }

    // ---- Unknown (5xx) ---------------------------------------------------

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ApiResponse<?>> handleUnexpected(Exception e) {
        // Full stack only goes to log; the user sees a generic message so we
        // don't leak SQL fragments, file paths, or internal class names.
        log.error("unhandled exception", e);
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(ApiResponse.error(500, "服务器内部错误"));
    }
}

package com.stock.exception;

/**
 * Caller-safe error: the message is shown to the end user verbatim.
 *
 * Throw this for validation / business-rule failures whose cause is obvious
 * from the message ("用户名已存在", "缺少股票代码"). For unexpected failures
 * let any other exception propagate — {@link GlobalExceptionHandler} will
 * log the stack trace and return a generic message instead of leaking it.
 */
public class BusinessException extends RuntimeException {

    private final int code;

    public BusinessException(String message) {
        this(400, message);
    }

    public BusinessException(int code, String message) {
        super(message);
        this.code = code;
    }

    public int getCode() {
        return code;
    }
}

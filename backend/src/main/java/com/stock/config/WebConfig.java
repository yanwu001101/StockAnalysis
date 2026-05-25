package com.stock.config;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebConfig implements WebMvcConfigurer {

    private final AuthInterceptor authInterceptor;
    private final DataTimeCleanupInterceptor dataTimeCleanupInterceptor;
    private final AccessLogInterceptor accessLogInterceptor;

    public WebConfig(AuthInterceptor authInterceptor,
                     DataTimeCleanupInterceptor dataTimeCleanupInterceptor,
                     AccessLogInterceptor accessLogInterceptor) {
        this.authInterceptor = authInterceptor;
        this.dataTimeCleanupInterceptor = dataTimeCleanupInterceptor;
        this.accessLogInterceptor = accessLogInterceptor;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(accessLogInterceptor)
                .addPathPatterns("/api/**");
        registry.addInterceptor(authInterceptor)
                .addPathPatterns("/api/**")
                .excludePathPatterns("/api/user/login", "/api/user/register");
        registry.addInterceptor(dataTimeCleanupInterceptor)
                .addPathPatterns("/api/**");
    }
}

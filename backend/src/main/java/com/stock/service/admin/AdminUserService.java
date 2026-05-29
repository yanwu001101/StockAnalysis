package com.stock.service.admin;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.stock.exception.BusinessException;
import com.stock.mapper.UserMapper;
import com.stock.model.entity.User;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

import java.security.SecureRandom;
import java.time.LocalDateTime;
import java.util.HashMap;
import java.util.Map;

@Service
public class AdminUserService {

    private static final String PASSWORD_ALPHABET =
        "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789@#$%&*";
    private static final SecureRandom RNG = new SecureRandom();

    private final UserMapper userMapper;
    private final PasswordEncoder passwordEncoder;
    private final AdminAuditService audit;

    public AdminUserService(UserMapper userMapper, PasswordEncoder passwordEncoder,
                            AdminAuditService audit) {
        this.userMapper = userMapper;
        this.passwordEncoder = passwordEncoder;
        this.audit = audit;
    }

    public IPage<Map<String, Object>> page(int pageNum, int pageSize,
                                           String keyword, String role, Integer status) {
        LambdaQueryWrapper<User> w = new LambdaQueryWrapper<User>()
            .orderByDesc(User::getId);
        if (keyword != null && !keyword.isBlank()) {
            w.and(q -> q.like(User::getUsername, keyword).or().like(User::getNickname, keyword));
        }
        if (role != null && !role.isBlank()) w.eq(User::getRole, role);
        if (status != null) w.eq(User::getStatus, status);

        IPage<User> p = userMapper.selectPage(new Page<>(pageNum, pageSize), w);
        return p.convert(this::toView);
    }

    public Map<String, Object> toggleStatus(Long id, HttpServletRequest req) {
        User u = mustFind(id);
        int next = (u.getStatus() != null && u.getStatus() == 1) ? 0 : 1;
        u.setStatus(next);
        userMapper.updateById(u);
        audit.record(req, next == 1 ? "USER_ENABLE" : "USER_DISABLE",
            "userId:" + id, Map.of("username", u.getUsername(), "status", next));
        return Map.of("id", id, "status", next);
    }

    public Map<String, Object> setRole(Long id, String role, Long operatorId, HttpServletRequest req) {
        if (!"ADMIN".equals(role) && !"USER".equals(role)) {
            throw new BusinessException("非法角色:" + role);
        }
        User u = mustFind(id);
        if (id.equals(operatorId) && "USER".equals(role)) {
            throw new BusinessException("不能把自己降级为 USER");
        }
        if ("USER".equals(role) && "ADMIN".equals(u.getRole())) {
            Long adminCount = userMapper.selectCount(
                new LambdaQueryWrapper<User>().eq(User::getRole, "ADMIN"));
            if (adminCount != null && adminCount <= 1) {
                throw new BusinessException("至少保留一个 ADMIN");
            }
        }
        u.setRole(role);
        userMapper.updateById(u);
        audit.record(req, "USER_SET_ROLE", "userId:" + id,
            Map.of("username", u.getUsername(), "role", role));
        return Map.of("id", id, "role", role);
    }

    public Map<String, Object> resetPassword(Long id, HttpServletRequest req) {
        User u = mustFind(id);
        String temp = generateTempPassword(12);
        u.setPassword(passwordEncoder.encode(temp));
        u.setMustChangePassword(1);
        userMapper.updateById(u);
        audit.record(req, "USER_RESET_PASSWORD", "userId:" + id,
            Map.of("username", u.getUsername()));
        // NOTE: tempPassword is returned ONCE to admin only; never persist plaintext.
        Map<String, Object> resp = new HashMap<>();
        resp.put("id", id);
        resp.put("username", u.getUsername());
        resp.put("tempPassword", temp);
        return resp;
    }

    public void softDelete(Long id, Long operatorId, HttpServletRequest req) {
        if (id.equals(operatorId)) {
            throw new BusinessException("不能删除自己");
        }
        User u = mustFind(id);
        userMapper.deleteById(id);
        audit.record(req, "USER_DELETE", "userId:" + id,
            Map.of("username", u.getUsername()));
    }

    public Map<String, Object> stats() {
        Long total = userMapper.selectCount(null);
        Long admins = userMapper.selectCount(
            new LambdaQueryWrapper<User>().eq(User::getRole, "ADMIN"));
        Long disabled = userMapper.selectCount(
            new LambdaQueryWrapper<User>().eq(User::getStatus, 0));
        LocalDateTime startOfToday = LocalDateTime.now().toLocalDate().atStartOfDay();
        Long todayNew = userMapper.selectCount(
            new LambdaQueryWrapper<User>().ge(User::getCreatedAt, startOfToday));
        return Map.of(
            "total", total == null ? 0 : total,
            "admins", admins == null ? 0 : admins,
            "disabled", disabled == null ? 0 : disabled,
            "todayNew", todayNew == null ? 0 : todayNew
        );
    }

    private User mustFind(Long id) {
        User u = userMapper.selectById(id);
        if (u == null) throw new BusinessException(404, "用户不存在");
        return u;
    }

    private Map<String, Object> toView(User u) {
        Map<String, Object> m = new HashMap<>();
        m.put("id", u.getId());
        m.put("username", u.getUsername());
        m.put("nickname", u.getNickname());
        m.put("role", u.getRole());
        m.put("status", u.getStatus());
        m.put("lastLoginAt", u.getLastLoginAt());
        m.put("mustChangePassword",
            u.getMustChangePassword() != null && u.getMustChangePassword() == 1);
        m.put("createdAt", u.getCreatedAt());
        return m;
    }

    private static String generateTempPassword(int len) {
        StringBuilder sb = new StringBuilder(len);
        for (int i = 0; i < len; i++) {
            sb.append(PASSWORD_ALPHABET.charAt(RNG.nextInt(PASSWORD_ALPHABET.length())));
        }
        return sb.toString();
    }
}

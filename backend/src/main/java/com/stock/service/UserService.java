package com.stock.service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.stock.config.JwtConfig;
import com.stock.mapper.UserMapper;
import com.stock.mapper.WatchlistGroupMapper;
import com.stock.mapper.WatchlistMapper;
import com.stock.model.entity.User;
import com.stock.model.entity.Watchlist;
import com.stock.model.entity.WatchlistGroup;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

import java.util.*;

@Service
public class UserService {

    private final UserMapper userMapper;
    private final WatchlistGroupMapper groupMapper;
    private final WatchlistMapper watchlistMapper;
    private final JwtConfig jwtConfig;
    private final PasswordEncoder passwordEncoder;

    public UserService(UserMapper userMapper, WatchlistGroupMapper groupMapper,
                       WatchlistMapper watchlistMapper, JwtConfig jwtConfig,
                       PasswordEncoder passwordEncoder) {
        this.userMapper = userMapper;
        this.groupMapper = groupMapper;
        this.watchlistMapper = watchlistMapper;
        this.jwtConfig = jwtConfig;
        this.passwordEncoder = passwordEncoder;
    }

    public Map<String, Object> register(String username, String password, String nickname) {
        User existing = userMapper.selectOne(
            new LambdaQueryWrapper<User>().eq(User::getUsername, username));
        if (existing != null) {
            throw new RuntimeException("用户名已存在");
        }

        User user = new User();
        user.setUsername(username);
        user.setPassword(passwordEncoder.encode(password));
        user.setNickname(nickname != null ? nickname : username);
        userMapper.insert(user);

        // Create default watchlist group
        WatchlistGroup group = new WatchlistGroup();
        group.setUserId(user.getId());
        group.setName("默认分组");
        groupMapper.insert(group);

        Map<String, Object> result = new HashMap<>();
        result.put("userId", user.getId());
        result.put("username", user.getUsername());
        return result;
    }

    public Map<String, Object> login(String username, String password) {
        User user = userMapper.selectOne(
            new LambdaQueryWrapper<User>().eq(User::getUsername, username));
        if (user == null || !passwordEncoder.matches(password, user.getPassword())) {
            throw new RuntimeException("用户名或密码错误");
        }

        String token = jwtConfig.generateToken(user.getId(), user.getUsername());
        Map<String, Object> result = new HashMap<>();
        result.put("token", token);
        Map<String, Object> userInfo = new HashMap<>();
        userInfo.put("id", user.getId());
        userInfo.put("username", user.getUsername());
        userInfo.put("nickname", user.getNickname());
        result.put("user", userInfo);
        return result;
    }

    public User getUserById(Long userId) {
        return userMapper.selectById(userId);
    }

    public List<Map<String, Object>> getWatchlists(Long userId) {
        List<WatchlistGroup> groups = groupMapper.selectList(
            new LambdaQueryWrapper<WatchlistGroup>().eq(WatchlistGroup::getUserId, userId));

        List<Map<String, Object>> result = new ArrayList<>();
        for (WatchlistGroup group : groups) {
            Map<String, Object> g = new HashMap<>();
            g.put("id", group.getId());
            g.put("name", group.getName());

            List<Watchlist> items = watchlistMapper.selectList(
                new LambdaQueryWrapper<Watchlist>()
                    .eq(Watchlist::getGroupId, group.getId())
                    .orderByDesc(Watchlist::getCreatedAt));
            g.put("stocks", items);
            result.add(g);
        }
        return result;
    }

    public void addToWatchlist(Long userId, Long groupId, String code, String name) {
        // Normalize: if caller doesn't know a real group id (commonly 0 from the
        // detail page's quick-add button), or the group doesn't belong to this
        // user, fall back to the user's default group, creating one if missing.
        WatchlistGroup group = null;
        if (groupId != null && groupId > 0) {
            group = groupMapper.selectOne(
                new LambdaQueryWrapper<WatchlistGroup>()
                    .eq(WatchlistGroup::getId, groupId)
                    .eq(WatchlistGroup::getUserId, userId));
        }
        if (group == null) {
            group = groupMapper.selectOne(
                new LambdaQueryWrapper<WatchlistGroup>()
                    .eq(WatchlistGroup::getUserId, userId)
                    .orderByAsc(WatchlistGroup::getId)
                    .last("LIMIT 1"));
        }
        if (group == null) {
            group = new WatchlistGroup();
            group.setUserId(userId);
            group.setName("默认分组");
            groupMapper.insert(group);
        }

        // Idempotent + revive soft-deleted: bypass @TableLogic to see ALL rows
        // including deleted=1 ones (they still hold the UNIQUE index slot).
        Watchlist existing = watchlistMapper.findByGroupAndCodeRaw(group.getId(), code);
        if (existing != null) {
            if (existing.getDeleted() != null && existing.getDeleted() == 1) {
                watchlistMapper.revive(existing.getId(), name);
            }
            return;
        }

        Watchlist item = new Watchlist();
        item.setUserId(userId);
        item.setGroupId(group.getId());
        item.setStockCode(code);
        item.setStockName(name != null ? name : "");
        watchlistMapper.insert(item);
    }

    public void removeFromWatchlist(Long userId, Long groupId, String code) {
        // Soft-target: prefer the (group, code) pair the caller specified, but if
        // the row isn't there (e.g. dirty group_id=0 legacy data, or the user
        // calls from a context that doesn't know the group), fall back to
        // (userId, code) so the action is always idempotent and never blocked.
        LambdaQueryWrapper<Watchlist> w = new LambdaQueryWrapper<Watchlist>()
            .eq(Watchlist::getStockCode, code);
        if (groupId != null && groupId > 0) {
            w.eq(Watchlist::getGroupId, groupId);
        } else if (userId != null) {
            w.eq(Watchlist::getUserId, userId);
        }
        watchlistMapper.delete(w);
    }

    /** @deprecated kept for ABI; routes through the userId-aware overload. */
    @Deprecated
    public void removeFromWatchlist(Long groupId, String code) {
        removeFromWatchlist(null, groupId, code);
    }

    public WatchlistGroup createGroup(Long userId, String name) {
        WatchlistGroup group = new WatchlistGroup();
        group.setUserId(userId);
        group.setName(name);
        groupMapper.insert(group);
        return group;
    }
}

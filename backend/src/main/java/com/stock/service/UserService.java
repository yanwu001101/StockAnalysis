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
        Watchlist item = new Watchlist();
        item.setUserId(userId);
        item.setGroupId(groupId);
        item.setStockCode(code);
        item.setStockName(name != null ? name : "");
        watchlistMapper.insert(item);
    }

    public void removeFromWatchlist(Long groupId, String code) {
        watchlistMapper.delete(
            new LambdaQueryWrapper<Watchlist>()
                .eq(Watchlist::getGroupId, groupId)
                .eq(Watchlist::getStockCode, code));
    }

    public WatchlistGroup createGroup(Long userId, String name) {
        WatchlistGroup group = new WatchlistGroup();
        group.setUserId(userId);
        group.setName(name);
        groupMapper.insert(group);
        return group;
    }
}

package cache

import (
	"context"
	"encoding/json"
	"time"

	"github.com/redis/go-redis/v9"
)

type Client struct {
	rdb        *redis.Client
	defaultTTL time.Duration
}

// LinkValue is intentionally minimal - only what the redirect hot path
// needs, not the whole links row.
type LinkValue struct {
	LongURL   string     `json:"long_url"`
	ExpiresAt *time.Time `json:"expires_at"`
}

func New(redisURL string, defaultTTLSeconds int) (*Client, error) {
	opt, err := redis.ParseURL(redisURL)
	if err != nil {
		return nil, err
	}
	return &Client{
		rdb:        redis.NewClient(opt),
		defaultTTL: time.Duration(defaultTTLSeconds) * time.Second,
	}, nil
}

func key(shortCode string) string {
	return "link:" + shortCode
}

func (c *Client) GetLink(ctx context.Context, shortCode string) (*LinkValue, error) {
	raw, err := c.rdb.Get(ctx, key(shortCode)).Result()
	if err == redis.Nil {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}

	var v LinkValue
	if err := json.Unmarshal([]byte(raw), &v); err != nil {
		return nil, err
	}
	return &v, nil
}

func (c *Client) SetLink(ctx context.Context, shortCode, longURL string, expiresAt *time.Time) error {
	data, err := json.Marshal(LinkValue{LongURL: longURL, ExpiresAt: expiresAt})
	if err != nil {
		return err
	}

	ttl := c.defaultTTL
	if expiresAt != nil {
		if untilExpiry := time.Until(*expiresAt); untilExpiry < ttl {
			ttl = untilExpiry
		}
		if ttl < time.Second {
			ttl = time.Second
		}
	}

	return c.rdb.Set(ctx, key(shortCode), data, ttl).Err()
}

package config

import (
	"os"
	"strconv"
)

type Settings struct {
	DatabaseURL            string
	RedisURL               string
	BaseURL                string
	DefaultCacheTTLSeconds int
}

func Load() Settings {
	return Settings{
		DatabaseURL:            getEnv("DATABASE_URL", "postgres://postgres:postgres@localhost:5434/urlshortener"),
		RedisURL:               getEnv("REDIS_URL", "redis://localhost:6381/0"),
		BaseURL:                getEnv("BASE_URL", "http://localhost:8002"),
		DefaultCacheTTLSeconds: getEnvInt("DEFAULT_CACHE_TTL_SECONDS", 24*3600),
	}
}

func getEnv(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func getEnvInt(key string, def int) int {
	if v := os.Getenv(key); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
	}
	return def
}

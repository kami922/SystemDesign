package config

import (
	"os"
	"strconv"
)

type Settings struct {
	DefaultLimit         int
	DefaultWindowSeconds float64
	StorageBackend       string
	RedisURL             string
	Port                 string
}

func Load() Settings {
	return Settings{
		DefaultLimit:         getEnvInt("RATE_LIMIT_DEFAULT_LIMIT", 10),
		DefaultWindowSeconds: getEnvFloat("RATE_LIMIT_DEFAULT_WINDOW_SECONDS", 10),
		StorageBackend:       getEnv("STORAGE_BACKEND", "memory"),
		RedisURL:             getEnv("REDIS_URL", "redis://localhost:6380/0"),
		Port:                 getEnv("PORT", "8080"),
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

func getEnvFloat(key string, def float64) float64 {
	if v := os.Getenv(key); v != "" {
		if f, err := strconv.ParseFloat(v, 64); err == nil {
			return f
		}
	}
	return def
}

// The v0.4 benchmark service in Go with chi, go-redis and go-sql-driver/mysql: the same
// routes and behaviour as bench/v04/users.tin.
package main

import (
	"database/sql"
	"encoding/json"
	"errors"
	"log"
	"net/http"
	"os"
	"strconv"
	"time"

	"github.com/go-chi/chi/v5"
	_ "github.com/go-sql-driver/mysql"
	"github.com/redis/go-redis/v9"
)

type User struct {
	ID      int64   `json:"id"`
	Name    string  `json:"name"`
	Email   string  `json:"email"`
	Score   float64 `json:"score"`
	Created string  `json:"created"`
}

func main() {
	rdb := redis.NewClient(&redis.Options{Addr: os.Getenv("REDIS_ADDR")})
	dsn := os.Getenv("MYSQL_USER") + ":" + os.Getenv("MYSQL_PASSWORD") + "@tcp(" + os.Getenv("MYSQL_ADDR") + ")/" + os.Getenv("MYSQL_DATABASE")
	db, err := sql.Open("mysql", dsn)
	if err != nil {
		log.Fatal(err)
	}
	db.SetMaxOpenConns(64)
	db.SetMaxIdleConns(64)
	stmt, err := db.Prepare("SELECT id, name, email, score, created FROM users WHERE id = ?")
	if err != nil {
		log.Fatal(err)
	}

	r := chi.NewRouter()
	r.Get("/users/{id}", func(w http.ResponseWriter, req *http.Request) {
		id, err := strconv.ParseInt(chi.URLParam(req, "id"), 10, 64)
		if err != nil {
			http.Error(w, "no such user", http.StatusNotFound)
			return
		}
		ctx := req.Context()
		key := "user:" + strconv.FormatInt(id, 10)
		v, err := rdb.Get(ctx, key).Result()
		if err == nil {
			w.Header().Set("Content-Type", "application/json")
			w.Write([]byte(v))
			return
		}
		if !errors.Is(err, redis.Nil) {
			http.Error(w, err.Error(), http.StatusBadGateway)
			return
		}
		var u User
		err = stmt.QueryRowContext(ctx, id).Scan(&u.ID, &u.Name, &u.Email, &u.Score, &u.Created)
		if errors.Is(err, sql.ErrNoRows) {
			http.Error(w, "no such user", http.StatusNotFound)
			return
		}
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadGateway)
			return
		}
		body, _ := json.Marshal(u)
		if err := rdb.Set(ctx, key, body, 60*time.Second).Err(); err != nil {
			http.Error(w, err.Error(), http.StatusBadGateway)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.Write(body)
	})
	r.Get("/db/users/{id}", func(w http.ResponseWriter, req *http.Request) {
		id, err := strconv.ParseInt(chi.URLParam(req, "id"), 10, 64)
		if err != nil {
			http.Error(w, "no such user", http.StatusNotFound)
			return
		}
		var u User
		err = stmt.QueryRowContext(req.Context(), id).Scan(&u.ID, &u.Name, &u.Email, &u.Score, &u.Created)
		if errors.Is(err, sql.ErrNoRows) {
			http.Error(w, "no such user", http.StatusNotFound)
			return
		}
		if err != nil {
			http.Error(w, err.Error(), http.StatusBadGateway)
			return
		}
		body, _ := json.Marshal(u)
		w.Header().Set("Content-Type", "application/json")
		w.Write(body)
	})
	r.Get("/slow", func(w http.ResponseWriter, req *http.Request) {
		select {
		case <-time.After(50 * time.Millisecond):
		case <-req.Context().Done():
			return
		}
		w.Write([]byte("slow"))
	})
	addr := ":9191"
	if p := os.Getenv("PORT"); p != "" {
		addr = ":" + p
	}
	log.Fatal(http.ListenAndServe(addr, r))
}

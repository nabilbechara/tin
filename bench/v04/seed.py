#!/usr/bin/env python3
"""Print SQL that creates the benchmark's users table with N rows (default 10000)."""
import sys

n = int(sys.argv[1]) if len(sys.argv) > 1 else 10000
print('DROP TABLE IF EXISTS users;')
print('CREATE TABLE users (id BIGINT PRIMARY KEY, name VARCHAR(64) NOT NULL, email VARCHAR(128) NOT NULL, '
      'score DOUBLE NOT NULL, created DATETIME NOT NULL);')
for start in range(1, n + 1, 1000):
    rows = []
    for i in range(start, min(start + 1000, n + 1)):
        rows.append("(%d, 'user %d', 'user%d@example.com', %d.%02d, '2024-%02d-%02d %02d:%02d:%02d')" %
                    (i, i, i, i % 1000, i % 100, i % 12 + 1, i % 28 + 1, i % 24, i % 60, (i * 7) % 60))
    print('INSERT INTO users VALUES %s;' % ', '.join(rows))

// Test-only native SQLite fault injector. Never copied into the candidate image.
package main

import (
	"database/sql"
	"fmt"
	"os"
	"strings"

	_ "github.com/mattn/go-sqlite3"
)

func main() {
	if len(os.Args) != 2 || (os.Args[1] != "client" && os.Args[1] != "schema") {
		os.Exit(2)
	}
	db, err := sql.Open("sqlite3", "file:/app/data/config.db?mode=rw&_busy_timeout=1000")
	if err != nil {
		os.Exit(2)
	}
	defer db.Close()
	if os.Args[1] == "schema" {
		if _, err = db.Exec("CREATE TABLE candidate_fault_only (id INTEGER)"); err != nil {
			os.Exit(2)
		}
	} else {
		rows, e := db.Query("SELECT name FROM sqlite_schema WHERE type='table'")
		if e != nil {
			os.Exit(2)
		}
		var tables []string
		for rows.Next() {
			var name string
			if rows.Scan(&name) != nil {
				os.Exit(2)
			}
			tables = append(tables, name)
		}
		if rows.Err() != nil || rows.Close() != nil {
			os.Exit(2)
		}
		changed := 0
		for _, name := range tables {
			var count int
			if db.QueryRow("SELECT count(*) FROM pragma_table_info(?) WHERE name='drop_excess_requests'", name).Scan(&count) != nil {
				os.Exit(2)
			}
			if count == 1 {
				identifier := `"` + strings.ReplaceAll(name, `"`, `""`) + `"`
				result, e := db.Exec("UPDATE " + identifier + " SET drop_excess_requests=CASE WHEN drop_excess_requests=0 THEN 1 ELSE 0 END")
				if e != nil {
					os.Exit(2)
				}
				n, e := result.RowsAffected()
				if e != nil || n != 1 {
					os.Exit(2)
				}
				changed++
			}
		}
		if changed != 1 {
			os.Exit(2)
		}
	}
	fmt.Println("MUTATED")
}

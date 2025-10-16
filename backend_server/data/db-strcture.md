# cards table
CREATE TABLE "cards" (
	"card_id"	TEXT,
	"is_guest"	BOOLEAN NOT NULL,
	"in_use"	BOOLEAN NOT NULL DEFAULT 0,
	PRIMARY KEY("card_id")
)

# registered_users table
CREATE TABLE registered_users (
          user_id TEXT PRIMARY KEY,
          full_name TEXT NOT NULL,
          card_id TEXT NOT NULL UNIQUE,
          other_info TEXT,
          FOREIGN KEY (card_id) REFERENCES cards(card_id)
)

# sessions table
CREATE TABLE sessions (
          session_id TEXT PRIMARY KEY,
          plate_text TEXT,
          vehicle_type TEXT,
          time_in TEXT NOT NULL,
          time_out TEXT,
          card_id TEXT NOT NULL,
          lane TEXT,
          status TEXT NOT NULL,
          fee REAL,
          FOREIGN KEY (card_id) REFERENCES cards(card_id)
        )
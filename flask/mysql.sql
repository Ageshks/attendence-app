CREATE TABLE user (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    is_admin BOOLEAN DEFAULT FALSE
);

CREATE TABLE attendance (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL,
    check_in_time DATETIME NOT NULL,
    check_out_time DATETIME DEFAULT NULL,
    FOREIGN KEY (username) REFERENCES user(username)
);

ALTER TABLE attendance ADD COLUMN latitude DOUBLE;
ALTER TABLE attendance ADD COLUMN longitude DOUBLE;


INSERT INTO user (username, password, is_admin) VALUES ('admin', '<hashed_password>', TRUE);

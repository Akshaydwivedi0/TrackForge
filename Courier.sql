create database courier;
use courier;
create table users( 
user_id int auto_increment primary key,
name varchar(100) not null,
email varchar(100) unique not null,
phone varchar(20),
Address varchar(255) not null,
password varchar(255) not null
);
CREATE TABLE delivery_agents (
    agent_id INT NOT NULL AUTO_INCREMENT,
    name VARCHAR(100) NOT NULL,
    phone VARCHAR(20) DEFAULT NULL,
    area VARCHAR(100) DEFAULT NULL,
    status VARCHAR(20) DEFAULT 'available',
    PRIMARY KEY (agent_id)
);
CREATE TABLE branches (
    branch_id INT NOT NULL AUTO_INCREMENT,
    branch_name VARCHAR(100) NOT NULL,
    location VARCHAR(255) NOT NULL,
    phone VARCHAR(20) DEFAULT NULL,
    PRIMARY KEY (branch_id)
);
create table parcels(
parcel_id int auto_increment primary key,
user_id int not null,
agent_id int,
branch_id int,
tracking_id int unique not null,
receiver_name varchar(100) not null,
receiver_phone varchar(20),
origin varchar(255) not null,
destination varchar(255) not null,
parcel_detail varchar(500),
booking_date timestamp default current_timestamp,
foreign key (user_id) references users(user_id),
foreign key (agent_id) references delivery_agents(agent_id),
foreign key (branch_id) references branches(branch_id));

create table tracking(
tracking_id int auto_increment primary key,
parcel_id int not null,
status varchar(50) not null,
location varchar(100) not null,
updated_at timestamp default current_timestamp,
foreign key (parcel_id) references parcels(parcel_id));
desc tracking;

create table payment(
payment_id int auto_increment primary key,
parcel_id int not null,
amount decimal(10,2) not null,
method varchar(30),
status varchar(30) default 'pending',
payment_date timestamp default current_timestamp,
foreign key (parcel_id) references parcels(parcel_id));
create table admin(
admin_id int auto_increment primary key,
name varchar(100) not null,
email varchar(100) unique not null,
password varchar(255) not null);
desc admin;
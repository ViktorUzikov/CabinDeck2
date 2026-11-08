import sqlite3 as sql


class Database:
    def __init__(self, filename: str):
        self.db = sql.connect(filename, autocommit=True)

        self.db.execute('''PRAGMA foreign_keys = ON;''')

        self.db.execute('''CREATE TABLE IF NOT EXISTS flights (
                id integer PRIMARY KEY autoincrement,
                number text NOT NULL,
                departure text NOT NULL,
                arrival text NOT NULL,
                date_time text NOT NULL
        ); ''')
        self.db.execute('''CREATE TABLE IF NOT EXISTS passengers (
                id integer PRIMARY KEY autoincrement,
                flight_id integer NOT NULL references flights(id) on delete cascade,
                full_name text NOT NULL,
                seat text,
                service_class text NOT NULL default 'Эконом',
                photo_path text,
                unique (flight_id, seat)
        );''')
        self.db.execute('''CREATE TABLE IF NOT EXISTS comments (
                id integer PRIMARY KEY autoincrement,
                passenger_id integer NOT NULL references passengers(id) on delete cascade,
                type text NOT NULL check (type in ('warning', 'note')),
                text text NOT NULL,
                created_at text NOT NULL default (datetime('now', 'localtime'))
        );''')
        self.db.execute('''CREATE TABLE IF NOT EXISTS food_items (
                id integer PRIMARY KEY autoincrement,
                flight_id integer NOT NULL references flights(id) on delete cascade,
                name text NOT NULL,
                quantity integer NOT NULL,
                unique (flight_id, name)
        );''')
        self.db.execute('create index if not exists idx_passengers_flight on passengers(flight_id);')
        self.db.execute('create index if not exists idx_comments_passenger on comments(passenger_id);')

    def _run(self, sql_script: str, params: tuple = ()):
        ret = self.db.execute(sql_script, params)

        self.db.commit()

        return ret

    def _all(self, sql_script: str, params: tuple = ()):
        return self.db.execute(sql_script, params).fetchall()

    def add_flight(self, number: str, departure: str, arrival: str, date_time: str):
        '''
        Adding flight to database

        :param number: Number of flight
        :param departure: Departure point
        :param arrival: Arrival point
        :param date_time: Datetime in Sqlite datetime format
        :return: Row id of created object
        '''
        return self._run(
            'INSERT INTO flights (number, departure, arrival, date_time) VALUES (?, ?, ?, ?)',
            (number, departure, arrival, date_time,),
        ).lastrowid

    def get_flights(self):
        '''
        Return all flights

        :return: All flights, that contains (id, number, departure, arrival, date_time)
        '''
        return self._all('SELECT * FROM flights order by date_time desc')

    def get_flight(self, flight_id: int):
        '''
        Return flight by id

        :param flight_id: Flight id
        :return:  Return flight by id, that contains (id, number, departure, arrival, date_time)
        '''

        return self.db.execute('SELECT * FROM flights where id = ?', (flight_id,)).fetchone()

    def delete_flight(self, flight_id: int):
        '''
        Delete flight by id

        :param flight_id: Flight id
        :return: Return result of execution
        '''

        return self._run('DELETE FROM flights WHERE id = ?', (flight_id,))

    def add_passenger(self, flight_id: int, full_name: str, seat: str, service_class: str, photo_path: str = 'None'):
        return self._run(
            f'INSERT INTO passengers (flight_id, full_name, seat, service_class, photo_path) values (?, ?, ?, ?, ?)',
            (flight_id, full_name, seat, service_class, photo_path)).lastrowid

    def get_passenger(self, passenger_id: int):
        return self.db.execute('SELECT * FROM passengers where id = ?', (passenger_id,)).fetchone()

    def get_passengers(self, flight_id: int):
        return self._all('SELECT * FROM passengers where flight_id = ? order by full_name',
                         (flight_id,))

    def change_passenger(self, passenger_id: int, full_name: str = 'None', seat: str = 'None',
                         service_class: str = 'None', photo_path: str = 'None'):
        fields = {
            'full_name': full_name,
            'seat': seat,
            'service_class': service_class,
            'photo_path': photo_path,
        }

        updates = {col: val for col, val in fields.items() if val != 'None'}

        if not updates:
            return 0

        set_updates = ', '.join(f'{col} = ?' for col in updates)

        return self._run(
            f'UPDATE passengers SET {set_updates} WHERE id = ?',
            (*updates.values(), passenger_id),
        ).rowcount

    def delete_passenger(self, passenger_id: int):
        return self._run('DELETE FROM passengers WHERE id = ?', (passenger_id,))

    def get_passenger_by_seat(self, flight_id: int, seat: str):
        return self.db.execute('SELECT * FROM passengers where flight_id = ? and seat = ?',
                               (flight_id, seat)).fetchone()

    def add_food(self, flight_id: int, name: str, quantity: int):
        return self._run(
            f'INSERT INTO food_items (flight_id, name, quantity) VALUES (?, ?, ?)',
            (flight_id, name, quantity,)
        ).lastrowid

    def get_food(self, food_id: int):
        return self.db.execute('SELECT name, quantity FROM food_items WHERE id = ?',
                               (food_id,)).fetchone()

    def get_foods(self, flight_id: int):
        return self._all('SELECT * FROM food_items WHERE flight_id = ?', (flight_id,))

    def change_food(self, food_id: int, name: str, quantity: int):
        fields = {
            'name': name,
            'quantity': quantity,
        }

        updates = {col: val for col, val in fields.items() if val != 'None'}

        if not updates:
            return 0

        set_updates = ', '.join(f'{col} = ?' for col in updates)

        return self._run(
            f'UPDATE food_items SET {set_updates} WHERE id = ?',
            (*updates.values(), food_id),
        ).rowcount

    def delete_food(self, food_id: int):
        return self._run('DELETE FROM food_items WHERE id = ?', (food_id,))

    def decrease_food_by_name(self, name: str):
        return self._run('UPDATE food_items SET quantity = quantity - 1 WHERE name = ?', (name,))

    def add_comment(self, passenger_id: int, comment: str, importance: bool):
        return self._run('INSERT INTO comments (passenger_id, text, type) VALUES (?, ?, ?)',
                         (passenger_id, comment, 'note' if not importance else 'warning'))

    def get_comments(self, passenger_id: int):
        return self._all('SELECT * FROM comments WHERE passenger_id = ?', (passenger_id,))

    def change_comment(self, comment_id: int, comment: str, importance: bool):
        fields = {
            'text': comment,
            'type': 'note' if not importance else 'warning',
        }

        updates = {col: val for col, val in fields.items() if val != 'None'}

        if not updates:
            return 0

        set_updates = ', '.join(f'{col} = ?' for col in updates)

        return self._run(
            f'UPDATE comments SET {set_updates} WHERE id = ?',
            (*updates.values(), comment_id),
        ).rowcount

    def get_comment(self, comment_id: int):
        return self.db.execute('SELECT text, type FROM comments WHERE id = ?', (comment_id,)).fetchone()

    def close(self):
        self.db.close()

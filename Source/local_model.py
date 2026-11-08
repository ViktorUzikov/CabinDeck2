from llama_cpp import Llama
from huggingface_hub import hf_hub_download
from PyQt6.QtCore import QThread, pyqtSignal
from json import dumps, loads
from .db import Database


class UnloadedModel(Exception):
    pass


history = []

llm = None

TOOLS = [
    {'type': 'function',
     'function': {
         'name': 'get_flights',
         'description': 'Retrieve all flights from the database. Return list with params for every flight in list: id, number, departure, arrival, datetime',
         'parameters': {
             'type': 'object',
             'properties': {},
             'required': []
         }
     }}
]

SYSTEM_PROMPT = '''
You are the built-in assistant of CabinDeck, a desktop app used by flight attendants (cabin crew).

LANGUAGE
- Always reply in the language the user writes in (usually Russian).

WHAT THE APP CAN DO (this is the complete list, never invent other features)
- Flights: create a new flight (number, departure, arrival, date and time) and switch between flights.
- Passengers: add a passenger to the selected flight (name, seat, service class, optional photo), view their data, change their photo.
- Seat map: every seat is a button. Red = taken, green = free. Left click selects the passenger in that seat. Right click on a taken seat opens a menu to give the passenger food.
- Food: per-flight list of food items with quantities. Items can be added, renamed, and their count changed. Giving food decreases the count by one; it cannot go below zero.
- Assistant (you): answers questions in the chat.

LIMITS
- If you are not sure about something, say so honestly. Do not make things up.
- Be short and practical. No long introductions.

OUTPUT FORMAT (very important)
- Output ONLY simple HTML. Never use Markdown: no *, **, #, `, ``` or - bullet lists. Never wrap the answer in code fences.
- Allowed tags only: <p>, <h3>, <b>, <i>, <u>, <br>, <ul>, <ol>, <li>, <span style="color:#RRGGBB">.
- Put every paragraph in <p>...</p>. Use <h3> for a title only when the answer is long.
- Always close every tag you open. Do not nest tags deeply.
- Use <b> for key words and <span style="color:#c62828"> for warnings. Do not use more than 2 colors.
- Do not output <html>, <head>, <body>, <style>, <script> or <div>.

EXAMPLE OF A CORRECT ANSWER:
<p>Чтобы выдать питание, нажмите <b>правой кнопкой</b> на занятое место и выберите блюдо.</p>

TOOL USAGE RULES

- When the user mentions a flight number, call get_flights.
- Find the exact matching flight number in the returned data.
- Never confuse flight number with flight ID.
- Use the database ID when calling other tools.
- Never invent flight IDs or database records.
- If multiple flights match, ask the user to clarify using departure, arrival or date.
- If no matching flight exists, inform the user.
- Extract function arguments from the user's natural language.
- If a required argument is missing, ask the user.
- Never guess passenger names, seat numbers or service classes.
- Validate all arguments before executing tools.
- After a successful operation, report the result.
- Never claim success if a tool returned an error.
- Never execute SQL directly.
- Only use explicitly provided tools.
- Do not call tools unnecessarily.
- You may call multiple tools sequentially when needed.
- Always use the result of a previous tool call when selecting arguments for the next call.
- If a tool fails, explain the error instead of pretending the operation succeeded.
'''


class StreamWorker(QThread):
    chunk = pyqtSignal(str)
    done = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, prompt: str):
        super().__init__()
        self.prompt = prompt
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        if llm is None:
            self.error.emit('Модель не загружена')

            # return

        worker_db = Database('database.db')

        known_flights = set()

        stream = None

        messages = ([{'role': 'system', 'content': SYSTEM_PROMPT}]
                    + history
                    + [{'role': 'user', 'content': self.prompt}])

        text = ''

        print('Начало обработки', flush=True)

        try:
            for i in range(5):
                print(f'Запрос к инструментам цикл {i}', flush=True)

                response = llm.create_chat_completion(
                    messages=messages,
                    tools=TOOLS,
                    tool_choice='auto',
                    # {'type': 'function', 'function': {'name': 'get_flights'}}
                    max_tokens=1024,
                    temperature=0.3,
                    stream=False
                )

                message = response['choices'][0]['message']

                message['content'] = message.get('content', '') or ''

                messages.append(message)

                print('MESSAGE', message, flush=True)
                print('FINISH REASON', response['choices'][0]['finish_reason'], flush=True)

                calls = message.get('tool_calls') or []

                print('CALLS', calls, flush=True)

                if not calls:
                    message = message['content'] or ''

                    break

                for call in calls:
                    name = call['function']['name']

                    args = loads(call['function']['arguments'])

                    try:
                        result = execute_tool(
                            name, args, worker_db, known_flights
                        )

                        content = dumps({'success': True, 'result': result}, ensure_ascii=False, default=str)
                    except Exception as e:
                        content = dumps({'success': False, 'error': str(e)}, ensure_ascii=False)

                    messages.append({'role': 'tool', 'tool_call_id': call['id'], 'content': content})

                    print(f'Called {name} with {content}', flush=True)


            else:
                raise RuntimeError('Превышен лимит вызовов инструментов')

            if self._stop:
                return

            if message:
                self.chunk.emit(message)

                text = message
            else:
                print('STREAM START', flush=True)

                stream = llm.create_chat_completion(messages, max_tokens=1024, temperature=0.3, stream=True)

                print('STREAM CREATED', flush=True)

                for part in stream:
                    if self._stop:
                        break

                    piece = part['choices'][0]['delta'].get('content') or ''

                    # print(piece, flush=True)

                    if piece:
                        text += piece

                        self.chunk.emit(piece)

                stream.close()

                stream = None
        except Exception as e:
            self.error.emit(str(e))

            return
        finally:
            worker_db.close()

            if stream is not None:
                stream.close()

        if self._stop:
            return

        history.append({'role': 'user', 'content': self.prompt})
        history.append({'role': 'assistant', 'content': text})

        history[:] = history[-10:]

        self.done.emit(text)

        print('STREAM FINISHED', flush=True)


def load_model():
    global llm

    model = hf_hub_download(
        repo_id='confamnode/Ministral-3-8B-Instruct-2512-GGUF',
        # For better experience use 8B, but on slow pc use 3B or for fastest work liquid 1.3B
        filename='Ministral-3-8B-Instruct-2512-Q4_K_M.gguf',
        local_dir='./Source/Model',
    )

    llm = Llama(
        model_path=model,
        n_ctx=4096,
        n_threads=6,
        n_gpu_layers=-1,
        n_batch=512,
        verbose=False,
    )

    llm.create_chat_completion(
        messages=[{'role': 'user', 'content': 'Привет'}],
        max_tokens=16,
        temperature=0,
    )


def is_loaded() -> bool:
    return llm is not None


def execute_tool(name, args, db, known_flights):
    print('Executing tool', name)

    if name == 'get_flights':
        flights = db.get_flights()

        known_flights.update(flight[0] for flight in flights)

        return flights

    raise ValueError(f'Unknown tool: {name}')

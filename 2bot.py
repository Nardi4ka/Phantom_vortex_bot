import discord
from discord import app_commands
import json
import os
import asyncio
import re
from flask import Flask
from collections import defaultdict
from datetime import datetime, timedelta
import threading

# ===== НАСТРОЙКА БОТА =====
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

class MyBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()
        print("✅ Слеш-команды синхронизированы")

bot = MyBot()

# ===== СИСТЕМА МОДЕРАЦИИ PHANTOM VORTEX =====
class PhantomVortexModSystem:
    def __init__(self):
        self.advertising_words = [
            'купить', 'продам', 'реклама', 'подписывайся', 'мой канал',
            'discord.gg/', 'http://', 'https://', 'бесплатно', 'скидка'
        ]
        
        self.explicit_words = [
            'секс', 'порно', 'xxx', 'porn', 'onlyfans', 'интим'
        ]
        
        self.threats_words = [
            'убью', 'зарежу', 'изобью', 'сдохни', 'вешайся', 'суицид'
        ]
        
        self.discrimination_words = [
            'нигер', 'ниггер', 'чурка', 'хач', 'жид', 'пидорас'
        ]

    async def analyze_message(self, message):
        if message.author.bot:
            return None
        
        content = message.content.lower()
        
        # 🔴 УГРОЗЫ - отправляем модераторам
        if any(threat in content for threat in self.threats_words):
            await self.report_to_moderators(message, "УГРОЗА", content)
            return "REPORT_ONLY"
        
        # 🔴 ДИСКРИМИНАЦИЯ - отправляем модераторам  
        if any(disc in content for disc in self.discrimination_words):
            await self.report_to_moderators(message, "ДИСКРИМИНАЦИЯ", content)
            return "REPORT_ONLY"
        
        # 🔵 АВТОМОДЕРАЦИЯ: Только реклама и плохие слова
        if any(ad in content for ad in self.advertising_words):
            return "ADVERTISING"
            
        if any(explicit in content for explicit in self.explicit_words):
            return "EXPLICIT"
            
        return None  # ✅ @everyone и массовые упоминания НЕ наказываются

    async def report_to_moderators(self, message, violation_type, content):
        """Отправляет репорт модераторам"""
        mod_channel = discord.utils.get(message.guild.channels, name="🛡️-репорты-модерации")
        if not mod_channel:
            overwrites = {
                message.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                message.guild.me: discord.PermissionOverwrite(read_messages=True)
            }
            for role in message.guild.roles:
                if role.permissions.manage_messages or role.permissions.administrator:
                    overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
            
            mod_channel = await message.guild.create_text_channel("🛡️-репорты-модерации", overwrites=overwrites)
        
        embed = discord.Embed(
            title=f"🚨 Требуется проверка: {violation_type}",
            color=0xff9900,
            timestamp=datetime.now()
        )
        embed.add_field(name="Автор", value=message.author.mention, inline=True)
        embed.add_field(name="Канал", value=message.channel.mention, inline=True)
        embed.add_field(name="Тип", value=violation_type, inline=True)
        embed.add_field(name="Сообщение", value=f"```{content[:500]}```", inline=False)
        
        await mod_channel.send(embed=embed)
        await mod_channel.send("@here")

    async def apply_punishment(self, user, violation_type, channel, reason=""):
        """Только для автоматических нарушений"""
        if violation_type in ["REPORT_ONLY"]:
            return  # Не наказываем, только репорт
            
        if violation_type == "ADVERTISING":
            await channel.send(f"🚫 {user.mention} реклама запрещена! Сообщение удалено.")
        
        elif violation_type == "EXPLICIT":
            await channel.send(f"🚫 {user.mention} контент 18+ запрещен! Сообщение удалено.")

mod_system = PhantomVortexModSystem()

# ===== СИСТЕМА СОХРАНЕНИЯ КОМАНД =====
def load_teams():
    try:
        if os.path.exists('teams.json'):
            with open('teams.json', 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            # АВТОМАТИЧЕСКОЕ ИСПРАВЛЕНИЕ ФОРМАТА
            fixed_data = {}
            for key, value in data.items():
                if isinstance(value, dict):
                    fixed_data[key] = value
                elif isinstance(value, str):
                    fixed_data[key] = {
                        'team_name': value,
                        'captain': 'Не указан', 
                        'game': 'dota 2'
                    }
                    
            print(f"✅ Загружено {len(fixed_data)} команд")
            return fixed_data
    except Exception as e:
        print(f"❌ Ошибка загрузки teams.json: {e}")
    return {}

def save_teams():
    try:
        with open('teams.json', 'w', encoding='utf-8') as f:
            json.dump(registered_teams, f, ensure_ascii=False, indent=2)
        print(f"✅ Сохранено {len(registered_teams)} команд")
    except Exception as e:
        print(f"❌ Ошибка сохранения teams.json: {e}")

registered_teams = load_teams()

# ===== СИСТЕМА ПРИГЛАШЕНИЙ =====
class TeamMemberSelect(discord.ui.UserSelect):
    def __init__(self, team_role_id):
        super().__init__(placeholder="Выберите участников команды...", max_values=4)
        self.team_role_id = team_role_id
    
    async def callback(self, interaction: discord.Interaction):
        role = interaction.guild.get_role(self.team_role_id)
        for user in self.values:
            await user.add_roles(role)
        
        await interaction.response.send_message(
            f"✅ Приглашены в команду: {', '.join([user.mention for user in self.values])}",
            ephemeral=True
        )

class OpponentMemberSelect(discord.ui.UserSelect):
    def __init__(self, opponent_role_id):
        super().__init__(placeholder="Выберите противников...", max_values=5)
        self.opponent_role_id = opponent_role_id
    
    async def callback(self, interaction: discord.Interaction):
        role = interaction.guild.get_role(self.opponent_role_id)
        for user in self.values:
            await user.add_roles(role)
        
        await interaction.response.send_message(
            f"🆚 Приглашены противники: {', '.join([user.mention for user in self.values])}",
            ephemeral=True
        )

class TeamInviteView(discord.ui.View):
    def __init__(self, team_role_id):
        super().__init__(timeout=60)
        self.team_role_id = team_role_id
        self.add_item(TeamMemberSelect(team_role_id))

class OpponentInviteView(discord.ui.View):
    def __init__(self, opponent_role_id):
        super().__init__(timeout=60)
        self.opponent_role_id = opponent_role_id
        self.add_item(OpponentMemberSelect(opponent_role_id))

class ClashInviteView(discord.ui.View):
    def __init__(self, team_role_id, opponent_role_id, team_name):
        super().__init__(timeout=None)
        self.team_role_id = team_role_id
        self.opponent_role_id = opponent_role_id
        self.team_name = team_name
    
    @discord.ui.button(label='➕ Пригласить свою команду', style=discord.ButtonStyle.success, custom_id='invite_team_btn')
    async def invite_team(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            f"**👥 Пригласите свою команду:**\n"
            f"Участники получат роль <@&{self.team_role_id}>\n"
            f"И смогут зайти в ваш клоз!",
            view=TeamInviteView(self.team_role_id),
            ephemeral=True
        )
    
    @discord.ui.button(label='🆚 Пригласить противников', style=discord.ButtonStyle.danger, custom_id='invite_opponents_btn')
    async def invite_opponents(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            f"**🆚 Пригласите противников:**\n"
            f"Они получат роль <@&{self.opponent_role_id}>\n"
            f"И смогут зайти в канал противников!",
            view=OpponentInviteView(self.opponent_role_id),
            ephemeral=True
        )

# ===== МОДАЛЬНЫЕ ОКНА И ФУНКЦИИ =====
class RegistrationModal(discord.ui.Modal, title='📝 Регистрация команды'):
    team_name = discord.ui.TextInput(label='Название команды', placeholder='Введите название команды...', max_length=50)
    captain_name = discord.ui.TextInput(label='Имя капитана', placeholder='Ваш игровой никнейм...', max_length=30)
    game_choice = discord.ui.TextInput(
        label='Игра (Dota 2 / CS2)', 
        placeholder='Напишите Dota 2 или CS2...', 
        max_length=10
    )

    async def on_submit(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        
        game = self.game_choice.value.strip().lower()
        if game not in ['dota 2', 'cs2']:
            await interaction.response.send_message(
                "❌ Неверная игра! Выберите: **Dota 2** или **CS2**", 
                ephemeral=True
            )
            return
        
        if user_id in registered_teams:
            await interaction.response.send_message(
                f"❌ Вы уже зарегистрированы как **{registered_teams[user_id]['team_name']}**!", 
                ephemeral=True
            )
            return
        
        registered_teams[user_id] = {
            'team_name': self.team_name.value,
            'captain': self.captain_name.value,
            'game': game
        }
        save_teams()
        
        embed = discord.Embed(
            title="✅ Регистрация завершена!", 
            description=f"Команда **{self.team_name.value}** зарегистрирована!", 
            color=0x2ecc71
        )
        embed.add_field(name="👑 Капитан:", value=self.captain_name.value, inline=True)
        embed.add_field(name="🎮 Игра:", value=game.upper(), inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

# ===== ФУНКЦИЯ СОЗДАНИЯ КЛОЗА С ИСТОЧНИКАМИ =====
async def create_clash(interaction: discord.Interaction, button: discord.ui.Button):
    user_id = str(interaction.user.id)
    
    # Проверяем лимит клозов (2 на пользователя)
    user_closes = sum(1 for category in interaction.guild.categories 
                     if f"🎮 {interaction.user.name}" in category.name)
    if user_closes >= 2:
        await interaction.response.send_message(
            "❌ У вас уже есть 2 активных клоза! Дождитесь их удаления.", 
            ephemeral=True
        )
        return
    
    # Получаем данные команды
    team_data = registered_teams.get(user_id, {})
    team_name = team_data.get('team_name', 'Неизвестно')
    game_type = team_data.get('game', 'dota 2')
    
    # Создаем приватные каналы
    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(connect=False, read_messages=False),
        interaction.user: discord.PermissionOverwrite(connect=True, read_messages=True, send_messages=True),
        interaction.guild.me: discord.PermissionOverwrite(connect=True, read_messages=True, send_messages=True)
    }
    
    # Создаем категорию
    category_name = f"🎮 {interaction.user.name} | 4h"
    category = await interaction.guild.create_category_channel(
        name=category_name,
        overwrites=overwrites,
        position=0
    )
    
    # Создаем каналы
    voice_channel = await category.create_voice_channel(name="🔊 Голосовой чат", user_limit=10)
    text_channel = await category.create_text_channel(name="💬 Общий чат")
    info_channel = await category.create_text_channel(name="📚 Полезные источники")
    
    # Добавляем источники в зависимости от игры
    sources_embed = discord.Embed(title="📚 Полезные источники", color=0x3498db)
    
    if game_type.lower() == "dota 2":
        sources_embed.description = "**Для Dota 2:**"
        sources_embed.add_field(
            name="📊 Статистика и аналитика",
            value="• [DotaBuff](https://www.dotabuff.com)\n• [Stratz](https://stratz.com)\n• [Dota2ProTracker](https://www.dota2protracker.com)",
            inline=False
        )
    elif game_type.lower() == "cs2":
        sources_embed.description = "**Для CS2:**"
        sources_embed.add_field(
            name="📊 Статистика и аналитика", 
            value="• [HLTV](https://www.hltv.org)\n• [Leetify](https://leetify.com)\n• [ScopeGG](https://scope.gg)",
            inline=False
        )
    
    sources_message = await info_channel.send(embed=sources_embed)
    await sources_message.pin()
    
    # Отправляем приветственное сообщение
    embed = discord.Embed(
        title="🎮 Клоз создан!",
        description=(
            "**Доступно только вам и приглашенным друзьям**\n\n"
            "**Каналы:**\n"
            f"• {voice_channel.mention} - голосовой чат\n"
            f"• {text_channel.mention} - текстовый чат\n"
            f"• {info_channel.mention} - полезные источники\n\n"
            "⏰ **Автоматически удалится через 4 часа**\n"
            "👥 **Чтобы пригласить друзей:**\n"
            "1. Нажмите на канал правой кнопкой\n"
            "2. 'Пригласить участников'\n"
            "3. Выберите друзей"
        ),
        color=0x00ff00
    )
    
    await text_channel.send(embed=embed)
    
    # Отправляем подтверждение
    await interaction.response.send_message(
        f"✅ Клоз создан! {category.mention}\n"
        f"• Удалится автоматически через 4 часа", 
        ephemeral=True
    )
    
    # Запускаем таймер удаления через 4 часа
    asyncio.create_task(delete_close_after_delay(category, 4 * 60 * 60))

# ===== ФУНКЦИЯ АВТОУДАЛЕНИЯ КЛОЗОВ =====
async def delete_close_after_delay(category, delay_seconds):
    await asyncio.sleep(delay_seconds)
    
    try:
        # Проверяем, пустые ли каналы
        empty = True
        for channel in category.channels:
            if isinstance(channel, discord.VoiceChannel) and len(channel.members) > 0:
                empty = False
                break
        
        if empty:
            # Удаляем все каналы в категории
            for channel in category.channels:
                await channel.delete()
            await category.delete()
        else:
            # Если есть люди - проверяем еще через 1 час
            asyncio.create_task(delete_close_after_delay(category, 3600))
    except discord.NotFound:
        pass  # Категория уже удалена
    except Exception as e:
        print(f"❌ Ошибка удаления клоза: {e}")

# ===== ОСНОВНАЯ ПАНЕЛЬ =====
class MainPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label='📝 Регистрация команды', style=discord.ButtonStyle.primary, custom_id='register_btn')
    async def register_team(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RegistrationModal())
    
    @discord.ui.button(label='🎮 Создать клоз ', style=discord.ButtonStyle.success, custom_id='create_clash_btn')
    async def create_clash(self, interaction: discord.Interaction, button: discord.ui.Button):
        await create_clash(interaction, button)
    
    @discord.ui.button(label='📊 Список команд', style=discord.ButtonStyle.secondary, custom_id='teams_list_btn')
    async def show_teams(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not registered_teams:
            embed = discord.Embed(title="📊 Список команд", description="Пока никто не зарегистрировался", color=0xf39c12)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        teams_list = ""
        for user_id, team_data in registered_teams.items():
            user = await bot.fetch_user(int(user_id))
            username = user.name if user else "Неизвестный"
            teams_list += f"• **{team_data['team_name']}** ({team_data['game'].upper()}) - {username}\n"
        
        embed = discord.Embed(title="📊 Зарегистрированные команды", description=teams_list, color=0x2ecc71)
        embed.add_field(name="📈 Статистика:", value=f"Всего команд: **{len(registered_teams)}**", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

# ===== ПАНЕЛЬ МОДЕРАЦИИ =====
class AdminPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label='👁️ Просмотреть заявки', style=discord.ButtonStyle.primary, custom_id='view_apps_btn')
    async def view_applications(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not registered_teams:
            await interaction.response.send_message("❌ Нет зарегистрированных команд.", ephemeral=True)
            return
        
        embed = discord.Embed(title="📋 Все зарегистрированные команды", color=0x3498db)
        for user_id, team_data in registered_teams.items():
            user = await bot.fetch_user(int(user_id))
            username = user.name if user else "Неизвестный"
            embed.add_field(
                name=f"🏷️ {team_data['team_name']} ({team_data['game'].upper()})", 
                value=f"Капитан: {username}", 
                inline=False
            )
        
        embed.set_footer(text=f"Всего команд: {len(registered_teams)}")
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @discord.ui.button(label='📤 Экспорт в файл', style=discord.ButtonStyle.secondary, custom_id='export_btn')
    async def export_teams(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not registered_teams:
            await interaction.response.send_message("❌ Нет данных для экспорта.", ephemeral=True)
            return
        
        filename = f"teams_export_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
        with open(filename, 'w', encoding='utf-8') as f:
            for user_id, team_data in registered_teams.items():
                user = await bot.fetch_user(int(user_id))
                username = user.name if user else "Неизвестный"
                f.write(f"Команда: {team_data['team_name']} | Игра: {team_data['game']} | Капитан: {username}\n")
        
        await interaction.response.send_message(file=discord.File(filename), ephemeral=True)
        os.remove(filename)
    
    @discord.ui.button(label='🗑️ Очистить заявки', style=discord.ButtonStyle.danger, custom_id='clear_btn')
    async def clear_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not registered_teams:
            await interaction.response.send_message("❌ Нет данных для очистки.", ephemeral=True)
            return
        
        confirm_view = ConfirmClearView()
        await interaction.response.send_message("⚠️ Удалить ВСЕ зарегистрированные команды?", view=confirm_view, ephemeral=True)

class ConfirmClearView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=30)
    
    @discord.ui.button(label='✅ Да', style=discord.ButtonStyle.danger)
    async def confirm_clear(self, interaction: discord.Interaction, button: discord.ui.Button):
        global registered_teams
        count = len(registered_teams)
        registered_teams = {}
        save_teams()
        await interaction.response.send_message(f"✅ Удалено {count} команд!", ephemeral=True)
    
    @discord.ui.button(label='❌ Нет', style=discord.ButtonStyle.secondary)
    async def cancel_clear(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("❌ Очистка отменена.", ephemeral=True)

# ===== ОБРАБОТЧИКИ СОБЫТИЙ =====
@bot.event
async def on_ready():
    print(f'✅ Бот {bot.user} запущен!')
    print(f'✅ Загружено команд: {len(registered_teams)}')

@bot.event
async def on_message(message):
    violation = await mod_system.analyze_message(message)
    if violation:
        await message.delete()
        await mod_system.apply_punishment(message.author, violation, message.channel)
    
    await bot.process_commands(message)

# ===== КОМАНДЫ =====
@bot.tree.command(name="panel", description="📊 Установить панель для игроков")
async def setup_panel(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Нет прав!", ephemeral=True)
        return
    
    embed = discord.Embed(title="🎮 Панель управления командами", description="Все инструменты для организации игрового процесса", color=0x9b59b6)
    embed.add_field(name="📝 Регистрация команды", value="Зарегистрируйте команду для доступа ко всем функциям", inline=False)
    embed.add_field(name="🎮 Создать клоз ", value="Приватная комната на 4 часа для игр с друзьями", inline=False)
    embed.add_field(name="📊 Список команд", value="Посмотреть все зарегистрированные команды", inline=False)
    
    await interaction.channel.send(embed=embed, view=MainPanelView())
    await interaction.response.send_message("✅ Панель установлена!", ephemeral=True)

@bot.tree.command(name="modpanel", description="🛠️ Панель модерации")
@app_commands.checks.has_permissions(administrator=True)
async def admin_panel(interaction: discord.Interaction):
    embed = discord.Embed(title="🛠️ Панель модерации", description="Инструменты для управления заявками", color=0xe74c3c)
    embed.add_field(name="👁️ Просмотреть заявки", value="Список всех зарегистрированных команд", inline=False)
    embed.add_field(name="📤 Экспорт в файл", value="Скачать список команд", inline=False)
    embed.add_field(name="🗑️ Очистить заявки", value="Полная очистка базы", inline=False)
    
    await interaction.channel.send(embed=embed, view=AdminPanelView())
    await interaction.response.send_message("✅ Панель модерации установлена!", ephemeral=True)

@bot.tree.command(name="warn", description="Выдать предупреждение")
@app_commands.checks.has_permissions(manage_messages=True)
async def warn_user(interaction: discord.Interaction, пользователь: discord.Member, причина: str):
    await mod_system.apply_punishment(пользователь, "ADVERTISING", interaction.channel, причина)
    await interaction.response.send_message(f"✅ {пользователь.mention} получил предупреждение", ephemeral=True)

@bot.tree.command(name="clear_warns", description="Сбросить предупреждения")
@app_commands.checks.has_permissions(administrator=True)
async def clear_warnings(interaction: discord.Interaction, пользователь: discord.Member):
    embed = discord.Embed(title="✅ Предупреждения сброшены", color=0x2ecc71)
    embed.add_field(name="Участник", value=пользователь.mention, inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ===== МОНИТОРИНГ =====
app = Flask(__name__)

@app.route('/')
def home():
    return "ALIVE", 200

def run_server():
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

flask_thread = threading.Thread(target=run_server)
flask_thread.daemon = True
flask_thread.start()
print("✅ Мониторинг запущен на порту 5000")

# ===== ЗАПУСК =====
bot.run(os.getenv('TOKEN'))






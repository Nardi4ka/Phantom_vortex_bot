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
    if os.path.exists('teams.json'):
        try:
            with open('teams.json', 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_teams():
    with open('teams.json', 'w', encoding='utf-8') as f:
        json.dump(registered_teams, f, ensure_ascii=False, indent=2)

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

# ===== ФУНКЦИЯ СОЗДАНИЯ ПОЛНОЦЕННОГО КЛОЗА =====
async def create_full_clash(interaction: discord.Interaction, team_name: str, captain_name: str, game_type: str):
    game_display_names = {
        "dota 2": "Dota 2",
        "cs2": "CS2"
    }
    
    game_display = game_display_names.get(game_type.lower(), game_type.upper())
    category_name = f"🎮 {game_display} | {captain_name}"
    
    team_role = await interaction.guild.create_role(
        name=f"👥 {team_name}",
        color=discord.Color.green(),
        hoist=True
    )
    
    opponent_role = await interaction.guild.create_role(
        name=f"⚔️ {team_name}",
        color=discord.Color.red(),
        hoist=True
    )
    
    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False, connect=False),
        team_role: discord.PermissionOverwrite(read_messages=True, connect=True, send_messages=True),
        opponent_role: discord.PermissionOverwrite(read_messages=True, connect=True, send_messages=True),
        interaction.guild.me: discord.PermissionOverwrite(read_messages=True, connect=True, send_messages=True)
    }
    
    category = await interaction.guild.create_category(
        name=category_name,
        overwrites=overwrites
    )
    
    info_channel = await category.create_text_channel(f"📋-{team_name}-инфо")
    chat_channel = await category.create_text_channel(f"💬-{team_name}-чат")
    invite_channel = await category.create_text_channel(f"📩-приглашения")
    
    ally_voice = await category.create_voice_channel(
        name=f"🟢-союзники-{team_name}",
        user_limit=5
    )
    
    enemy_voice = await category.create_voice_channel(
        name=f"🔴-противники-{team_name}",
        user_limit=5
    )
    
    await interaction.user.add_roles(team_role)
    
    invite_embed = discord.Embed(
        title=f"🎮 Панель управления клозом {team_name}",
        description="Используйте кнопки ниже для приглашения участников",
        color=0x9b59b6
    )
    invite_embed.add_field(name="🟢 Союзники", value="Ваша команда", inline=True)
    invite_embed.add_field(name="🔴 Противники", value="Команда оппонентов", inline=True)
    invite_embed.add_field(name="🎮 Игра", value=game_display, inline=True)
    
    await invite_channel.send(embed=invite_embed, view=ClashInviteView(team_role.id, opponent_role.id, team_name))
    
    sources_embed = discord.Embed(
        title="📚 Полезные источники",
        color=0x3498db
    )
    
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
    
    asyncio.create_task(delete_close_after_delay(category, 4 * 60 * 60))
    
    return category

# ===== ФУНКЦИЯ АВТОУДАЛЕНИЯ КЛОЗОВ =====
async def delete_close_after_delay(category, delay_seconds):
    await asyncio.sleep(delay_seconds)
    
    try:
        for role in category.guild.roles:
            if "👥" in role.name or "⚔️" in role.name:
                role_team_name = role.name.split(' ', 1)[1] if ' ' in role.name else role.name
                if role_team_name in category.name:
                    await role.delete()
        
        for channel in category.channels:
            await channel.delete()
        
        await category.delete()
        
    except Exception as e:
        print(f"❌ Ошибка удаления клоза: {e}")

# ===== ОСНОВНАЯ ПАНЕЛЬ =====
class MainPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label='📝 Регистрация команды', style=discord.ButtonStyle.primary, custom_id='register_btn')
    async def register_team(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RegistrationModal())
    
    @discord.ui.button(label='🎮 Создать полноценный клоз', style=discord.ButtonStyle.success, custom_id='create_full_clash_btn')
    async def create_full_clash(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = str(interaction.user.id)
        
        if user_id not in registered_teams:
            await interaction.response.send_message(
                "❌ Сначала зарегистрируйте команду через кнопку '📝 Регистрация команды'!", 
                ephemeral=True
            )
            return
        
        team_data = registered_teams[user_id]
        
        user_closes = sum(1 for category in interaction.guild.categories 
                         if f"🎮 {interaction.user.display_name}" in category.name)
        if user_closes >= 2:
            await interaction.response.send_message(
                "❌ У вас уже есть 2 активных клозов! Дождитесь их удаления.", 
                ephemeral=True
            )
            return
        
        category = await create_full_clash(
            interaction, 
            team_data['team_name'],
            team_data['captain'], 
            team_data['game']
        )
        
        await interaction.response.send_message(
            f"✅ Полноценный клоз создан! {category.mention}\n"
            f"• 🟢 Войс для союзников (5 слотов)\n" 
            f"• 🔴 Войс для противников (5 слотов)\n"
            f"• 📚 Полезные источники\n"
            f"• 👥 Панель приглашения\n"
            f"• ⏰ Удалится через 4 часа", 
            ephemeral=True
        )
    
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
    embed.add_field(name="🎮 Создать полноценный клоз", value="Полноценная игровая комната с ролями, войсами и панелями", inline=False)
    embed.add_field(name="📊 Список команд", value="Посмотреть все зарегистрированные команды", inline=False)
    
    await interaction.channel.send(embed=embed, view=MainPanelView())
    await interaction.response.send_message("✅ Панель установлена!", ephemeral=True)

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




